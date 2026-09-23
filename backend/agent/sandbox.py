"""Sandboxed Python execution for the agent's `run_python` tool.

Each run gets a fresh temp directory, a stripped environment, hard resource
limits (CPU, memory, file size, process count), a wall-clock timeout, and — when
the host allows unprivileged user namespaces — no network access. When running
as root the child drops to `nobody`.

This is process-level isolation, not a VM. It stops runaway code and casual
misuse; for hostile multi-tenant workloads run it inside a container/VM too.
"""
import asyncio
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

CPU_SECONDS = int(os.environ.get("SANDBOX_CPU_SECONDS", "20"))
WALL_SECONDS = int(os.environ.get("SANDBOX_WALL_SECONDS", "30"))
MEMORY_BYTES = int(os.environ.get("SANDBOX_MEMORY_MB", "768")) * 1024 * 1024
FILE_BYTES = 20 * 1024 * 1024
MAX_OUTPUT = 12_000
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
ARTIFACT_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".csv", ".txt", ".json", ".md", ".html",
                 ".xlsx", ".docx", ".pptx", ".pdf", ".mp4"}
NOBODY = 65534

# Makes matplotlib (if installed) render headless and write its cache inside the sandbox.
_PRELUDE = "import os as _o\n_o.environ.setdefault('MPLBACKEND', 'Agg')\ndel _o\n"


@dataclass
class Artifact:
    name: str
    content_type: str
    data: bytes


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: Optional[int]
    timed_out: bool
    network_isolated: bool
    artifacts: List[Artifact] = field(default_factory=list)


def _world_executable(path: str) -> bool:
    """Whether an unprivileged user can reach and execute `path`."""
    p = Path(path)
    try:
        if not p.resolve().stat().st_mode & 0o001:
            return False
        # Check the directories as written (a venv symlink can sit in a private dir).
        return all(parent.stat().st_mode & 0o001 for parent in p.absolute().parents)
    except OSError:
        return False


@lru_cache(maxsize=1)
def python_executable() -> str:
    """Interpreter for sandboxed runs. The server's own venv is often under /root,
    which `nobody` cannot enter, so fall back to a system python3."""
    configured = os.environ.get("SANDBOX_PYTHON")
    if configured:
        return configured
    candidates = [sys.executable, shutil.which("python3") or "", "/usr/local/bin/python3", "/usr/bin/python3"]
    if not _drop_root():
        return sys.executable
    for c in candidates:
        if c and _world_executable(c):
            return c
    return sys.executable


def _drop_root() -> bool:
    return os.geteuid() == 0


@lru_cache(maxsize=1)
def network_isolation_available() -> bool:
    """True when `unshare -rn` works here (as the user the child will run as)."""
    if not shutil.which("unshare"):
        return False
    try:
        res = subprocess.run(
            ["unshare", "-rn", "true"], preexec_fn=_preexec if _drop_root() else None,
            capture_output=True, timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


def _preexec():
    os.setsid()
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_BYTES, FILE_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if _drop_root():
        os.setgroups([])
        os.setgid(NOBODY)
        os.setuid(NOBODY)
    # Applied after dropping root so it counts against `nobody`, not the server user.
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n… [truncated {len(text) - MAX_OUTPUT} chars]"


def _content_type(ext: str) -> str:
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
        ".svg": "image/svg+xml", ".webp": "image/webp", ".csv": "text/csv", ".json": "application/json",
        ".md": "text/markdown", ".html": "text/html", ".pdf": "application/pdf", ".mp4": "video/mp4",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(ext, "text/plain")


async def run_python(code: str) -> RunResult:
    workdir = Path(tempfile.mkdtemp(prefix="radha-sbx-"))
    try:
        if _drop_root():
            os.chown(workdir, NOBODY, NOBODY)
        script = workdir / "main.py"
        script.write_text(_PRELUDE + code)
        isolated = network_isolation_available()
        cmd = [python_executable(), "-I", str(script)]
        if isolated:
            cmd = ["unshare", "-rn"] + cmd
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(workdir), "TMPDIR": str(workdir),
               "MPLCONFIGDIR": str(workdir), "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"}

        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=workdir, env=env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, preexec_fn=_preexec,
        )
        timed_out = False
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=WALL_SECONDS)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = await proc.communicate()

        artifacts = []
        for path in sorted(workdir.rglob("*")):
            if path.is_file() and path.name != "main.py" and path.suffix.lower() in ARTIFACT_EXTS:
                if path.stat().st_size <= MAX_ARTIFACT_BYTES and len(artifacts) < 10:
                    artifacts.append(Artifact(path.name, _content_type(path.suffix.lower()), path.read_bytes()))

        return RunResult(
            stdout=_truncate(out.decode("utf-8", "replace")),
            stderr=_truncate(err.decode("utf-8", "replace")),
            exit_code=None if timed_out else proc.returncode,
            timed_out=timed_out,
            network_isolated=isolated,
            artifacts=artifacts,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
