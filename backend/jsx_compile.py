"""Real React apps in the App Builder: JSX, TypeScript and npm imports, with no build step for the user.

Apps are served file by file (the preview, the published site). A .jsx, .tsx or .ts file, or a .js file that
imports React, is compiled with esbuild when it is served, and its imports are made loadable by a browser:

    import { motion } from "framer-motion"   ->  "https://esm.sh/framer-motion"
    import App from "./App"                   ->  "./App.jsx"   (whichever file exists)
    import "./index.css"                      ->  a <link> added to the page

so a Vite-style project (index.html loading /src/main.jsx) runs as written, including one imported from GitHub.
When esbuild isn't installed the files are served unchanged, as before.
"""
import hashlib
import os
import posixpath
import re
import shutil
import subprocess
from collections import OrderedDict
from typing import Dict, Optional

COMPILED_EXTS = (".jsx", ".tsx", ".ts")
_RESOLVE_EXTS = (".jsx", ".tsx", ".ts", ".js", ".mjs")
_CACHE: "OrderedDict[str, str]" = OrderedDict()
_CACHE_SIZE = 300
_TIMEOUT = 20
_REACT_IMPORT = re.compile(r"""from\s+["']react(?:-dom)?(?:/[\w/-]*)?["']|<[A-Z][\w.]*[\s/>]""")
# import ... from "x" | export ... from "x" | import "x" | import("x")
_SPEC = re.compile(r"""((?:\bimport|\bexport)\b[^'"`;]*?\bfrom\s*|\bimport\s*\(?\s*)(["'])([^"'\n]+)\2""")
_CSS_IMPORT = re.compile(r"""^\s*import\s+(["'])([^"']+\.css)\1\s*;?\s*$""", re.MULTILINE)
_ESM = "https://esm.sh/"


def esbuild_path() -> Optional[str]:
    found = os.environ.get("ESBUILD_PATH") or shutil.which("esbuild")
    if found:
        return found
    bundled = "/opt/esbuild/node_modules/esbuild/bin/esbuild"
    return bundled if os.path.exists(bundled) else None


def available() -> bool:
    return esbuild_path() is not None


def needs_compile(path: str, content: str) -> bool:
    if path.endswith(COMPILED_EXTS):
        return True
    return path.endswith((".js", ".mjs")) and bool(_REACT_IMPORT.search(content))


def _loader(path: str) -> str:
    return {"tsx": "tsx", "ts": "ts"}.get(path.rsplit(".", 1)[-1], "jsx")


def _esbuild(source: str, loader: str) -> str:
    key = hashlib.sha256((loader + "\0" + source).encode("utf-8")).hexdigest()
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    proc = subprocess.run([esbuild_path(), f"--loader={loader}", "--jsx=automatic", "--format=esm",
                           "--target=es2020", "--log-level=error"],
                          input=source.encode("utf-8"), capture_output=True, timeout=_TIMEOUT)
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode("utf-8", "replace").strip()[:1500])
    out = proc.stdout.decode("utf-8")
    _CACHE[key] = out
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return out


def _resolve(base: str, spec: str, files: Dict[str, str]) -> Optional[str]:
    """The file a relative import names, with the extension a bundler would have added."""
    target = posixpath.normpath(posixpath.join(posixpath.dirname(base), spec)) if spec.startswith(".") \
        else spec.lstrip("/")
    if target in files:
        return target
    for ext in _RESOLVE_EXTS:
        if target + ext in files:
            return target + ext
    for ext in _RESOLVE_EXTS:
        if f"{target}/index{ext}" in files:
            return f"{target}/index{ext}"
    return None


def _relative(base: str, target: str) -> str:
    rel = posixpath.relpath(target, posixpath.dirname(base) or ".")
    return rel if rel.startswith(".") else "./" + rel


def rewrite_imports(path: str, code: str, files: Dict[str, str]) -> str:
    def css(m):
        href = m.group(2)
        return ("(()=>{const l=document.createElement('link');l.rel='stylesheet';"
                f"l.href=new URL({href!r},import.meta.url).href;document.head.appendChild(l)}})();")

    code = _CSS_IMPORT.sub(css, code)

    def spec(m):
        prefix, quote, name = m.groups()
        if re.match(r"^(https?:|data:|blob:)", name):
            return m.group(0)
        if name.startswith((".", "/")):
            found = _resolve(path, name, files)
            return f"{prefix}{quote}{_relative(path, found) if found else name}{quote}"
        return f"{prefix}{quote}{_ESM}{name}{quote}"

    return _SPEC.sub(spec, code)


def compile_file(path: str, files: Dict[str, str]) -> str:
    """The browser-ready JavaScript for `path`. A compile error becomes a script that reports it in the console,
    so the builder's error check and "Fix errors with AI" see it."""
    source = files[path]
    try:
        code = _esbuild(source, _loader(path))
    except (ValueError, subprocess.TimeoutExpired, OSError) as exc:
        message = f"{path}: {str(exc) or 'could not compile'}"
        return f"console.error({message!r}); throw new SyntaxError({message!r});\n"
    return rewrite_imports(path, code, files)


_ABS_REF = re.compile(r"""(\s(?:src|href)\s*=\s*)(["'])/(?!/)([^"']*)\2""", re.IGNORECASE)


def relative_html(path: str, html: str, files: Dict[str, str]) -> str:
    """Vite pages link /src/main.jsx from the site root; the preview and published sites live under a folder,
    so links to the app's own files are made relative."""
    def fix(m):
        target = m.group(3).split("?")[0].split("#")[0]
        if target in files or _resolve(path, "/" + target, files):
            return f"{m.group(1)}{m.group(2)}{_relative(path, target) if target else './'}{m.group(3)[len(target):]}{m.group(2)}"
        return m.group(0)
    return _ABS_REF.sub(fix, html)
