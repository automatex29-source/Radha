"""An app as one HTML file people can open from their computer (the builder's Download button).

Each page gets everything it needs written into it: its stylesheets as <style>, its scripts as <script> (React and
other module code bundled by esbuild, packages from esm.sh), the design kit's CSS and motion script, its fonts, and
the RADHA client pointed at this server so logins, data and AI keep working. A one-page app downloads as that
page alone; an app with several pages downloads as a ZIP of pages that each work on their own.
"""
import io
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from typing import Dict, Optional

import appdata
import apps
import jsx_compile
import site_images

_STYLE_LINK_RE = re.compile(r"""<link\b[^>]*\brel\s*=\s*["']?stylesheet["']?[^>]*>""", re.IGNORECASE)
_HREF_RE = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_SCRIPT_SRC_RE = re.compile(r"""<script\b([^>]*?)\bsrc\s*=\s*["']([^"']+)["']([^>]*)>\s*</script\s*>""", re.IGNORECASE)
_MODULE_RE = re.compile(r"""\btype\s*=\s*["']?module""", re.IGNORECASE)
_RELATIVE_IMPORT_RE = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*)["'](\.{1,2}/|/)""")
_BARE_SPEC_RE = re.compile(r"""((?:\bimport|\bexport)\b[^'"`;]*?\bfrom\s*|\bimport\s*\(?\s*)(["'])([^"'.\n/][^"'\n]*)\2""")
_CODE_EXTS = (".css", ".js", ".mjs", ".jsx", ".ts", ".tsx")


def _script(code: str) -> str:
    return code.replace("</script", "<\\/script")


def _style(css: str) -> str:
    return css.replace("</style", "<\\/style")


def _esm_urls(code: str) -> str:
    """Bare package imports ("react") as esm.sh URLs, which the browser can load from anywhere."""
    def sub(m):
        prefix, quote, name = m.groups()
        if re.match(r"^[a-z][a-z0-9+.-]*:", name):
            return m.group(0)
        return f"{prefix}{quote}{jsx_compile._ESM}{name}{quote}"
    return _BARE_SPEC_RE.sub(sub, code)


def _bundle_module(entry: str, files: Dict[str, str]) -> Optional[tuple]:
    """(js, css) for a module script and everything it imports, or None when esbuild isn't here or fails."""
    esbuild = jsx_compile.esbuild_path()
    if not esbuild:
        return None
    tmp = tempfile.mkdtemp(prefix="radha-bundle-")
    try:
        for path, content in files.items():
            target = os.path.join(tmp, "src", path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(_esm_urls(content) if path.endswith(_CODE_EXTS[1:]) else content)
        out = os.path.join(tmp, "out")
        proc = subprocess.run(
            [esbuild, os.path.join(tmp, "src", entry), "--bundle", "--format=esm", "--minify", "--target=es2020",
             "--jsx=automatic", f"--jsx-import-source={jsx_compile._ESM}react", "--loader:.js=jsx", "--external:https://*", "--external:http://*",
             "--log-level=error", f"--outdir={out}", "--entry-names=bundle"],
            capture_output=True, timeout=60, cwd=tmp)
        if proc.returncode != 0:
            return None
        def read(name):
            p = os.path.join(out, name)
            return open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        return read("bundle.js"), read("bundle.css")
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def page(files: Dict[str, str], path: str, app_id: Optional[str] = None, origin: str = "") -> tuple:
    """(html, inlined paths): the page at `path` with its own stylesheets and scripts written into it."""
    html = files[path]
    kit = apps.uses_kit(html)
    used = set()
    extra_css = []

    def style(m):
        href = _HREF_RE.search(m.group(0))
        target = apps._resolve(path, href.group(1)) if href else None
        if not target:
            return m.group(0)
        css = files.get(target)
        if css is None and target.endswith(apps.KIT_NAME):
            css = apps.KIT_CSS
        if css is None:
            return m.group(0)
        used.add(target)
        return f"<style>\n{_style(css)}\n</style>"

    def script(m):
        before, src, after = m.groups()
        target = apps._resolve(path, src)
        if not target or target not in files:
            return m.group(0)
        code = files[target]
        module = bool(_MODULE_RE.search(before + after)) or jsx_compile.needs_compile(target, code)
        if module and (_RELATIVE_IMPORT_RE.search(code) or jsx_compile.needs_compile(target, code)
                       or re.search(r"""^\s*import\s+["'][^"']+\.css["']""", code, re.MULTILINE)):
            built = _bundle_module(target, files)
            if built is None:
                return m.group(0)
            code, css = built
            if css:
                extra_css.append(css)
        elif module:
            code = _esm_urls(code)
        used.add(target)
        attrs = re.sub(r"\s+", " ", (before + after)).strip()
        attrs = re.sub(r"""\b(defer|async)\b""", "", attrs).strip()
        if module and not _MODULE_RE.search(attrs):
            attrs = (attrs + ' type="module"').strip()
        return f"<script{(' ' + attrs) if attrs else ''}>\n{_script(code)}\n</script>"

    html = _STYLE_LINK_RE.sub(style, html)
    html = _SCRIPT_SRC_RE.sub(script, html)
    if extra_css:
        html = apps._after_head(html, "<style>\n" + _style("\n".join(extra_css)) + "\n</style>")
    if kit:
        html = apps._before_body_end(apps._after_head(html, apps.font_tags(html)), f"<script>\n{_script(apps.KIT_JS)}\n</script>\n")
    if app_id and origin:
        html = apps._after_head(html, appdata.sdk_script(app_id, origin=origin))
    if not re.search(r"<meta[^>]+charset", html, re.IGNORECASE):
        html = apps._after_head(html, '<meta charset="utf-8">')
    return site_images.rewrite(html, origin), used


def pages(files: Dict[str, str]) -> list:
    return sorted(p for p in files if p.endswith((".html", ".htm")) and not p.startswith(("node_modules/", "dist/")))


def single_file(files: Dict[str, str], app_id: Optional[str] = None, origin: str = "") -> Optional[str]:
    """The whole app as one HTML file, or None when it has more than one page."""
    found = pages(files)
    if len(found) != 1:
        return None
    return page(files, found[0], app_id, origin)[0]


def pages_zip(files: Dict[str, str], root: str, app_id: Optional[str] = None, origin: str = "") -> bytes:
    """A ZIP of the app's pages, each one complete on its own, plus any files they didn't take in (pictures, data)."""
    out: Dict[str, str] = {}
    used = set()
    for p in pages(files):
        out[p], inlined = page(files, p, app_id, origin)
        used |= inlined
    for p, content in files.items():
        if p in out or p in used or p.endswith((apps.KIT_NAME, apps.KIT_JS_NAME)):
            continue
        if p.split("/")[0] in ("node_modules", ".radha"):
            continue
        out[p] = site_images.rewrite(content, origin) if origin else content
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p, content in sorted(out.items()):
            zf.writestr(f"{root}/{p}", content)
    return buf.getvalue()
