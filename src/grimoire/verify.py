"""Verification: the only place Grimoire runs code from the repository.

Runs inside a temporary venv with no index access (``pip --no-index``). Dependencies
that cannot be installed offline yield UNVERIFIED, never ALIVE.
"""

from __future__ import annotations

import ast
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from . import requirements, scan
from .models import ProofResult

OUTPUT_CAP = 1024 * 1024  # 1 MiB of captured output
DEFAULT_TIMEOUT = 30.0
SETUP_TIMEOUT = 300.0


def copy_tree(src: str, dst: str) -> None:
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in scan.IGNORED_DIRS and not os.path.islink(os.path.join(dirpath, d)))
        rel = os.path.relpath(dirpath, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if not os.path.islink(full):
                shutil.copyfile(full, os.path.join(target, name))


def compile_check(root: str | os.PathLike[str]) -> list[str]:
    """ast-parse every Python file under root; returns failure descriptions (empty = all valid)."""
    failures: list[str] = []
    scanned = scan.scan_repo(root)
    for path in scanned.paths("python"):
        src, err = scan.read_source(root, path)
        if src is None:
            failures.append(f"{path}: {err.reason if err else 'unreadable'}")
            continue
        try:
            ast.parse(src.text, filename=path)
        except (SyntaxError, ValueError, RecursionError) as exc:
            failures.append(f"{path}:{getattr(exc, 'lineno', 0) or 0}: {exc}")
    return failures


def _minimal_env(home: str, venv: str | None) -> dict[str, str]:
    bin_dir = os.path.join(venv, "bin") if venv else ""
    return {
        "PATH": (bin_dir + os.pathsep if bin_dir else "") + "/usr/bin:/bin",
        "HOME": home,
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
    }


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _run(
    argv: list[str], cwd: str, env: dict[str, str], timeout: float
) -> tuple[int | None, str, bool]:
    """Run argv without a shell. Returns (exit_code, capped output, timed_out)."""
    proc = subprocess.Popen(
        argv,
        shell=False,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    chunks: list[bytes] = []

    def reader() -> None:
        size = 0
        assert proc.stdout is not None
        for block in iter(lambda: proc.stdout.read(4096), b""):
            if size < OUTPUT_CAP:
                chunks.append(block[: OUTPUT_CAP - size])
            size += len(block)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        _kill_group(proc)  # also reaps stray children of the process group
        proc.wait()
    thread.join(timeout=5)
    out = b"".join(chunks).decode("utf-8", errors="replace")
    return (None if timed_out else proc.returncode), out, timed_out


def _log_lines(text: str, *scrub: str) -> tuple[str, ...]:
    for s in scrub:
        text = text.replace(s, "<tmp>")
    return tuple(line.rstrip() for line in text.splitlines())


def verify(
    root: str | os.PathLike[str],
    entry: str | None,
    *,
    wheelhouse: str | os.PathLike[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ProofResult:
    """Prove that the project runs. Never raises for project problems; returns a status."""
    root_s = os.fspath(root)
    failures = compile_check(root_s)
    if failures:
        return ProofResult("STILL_DEAD", None, tuple(f"does not compile: {f}" for f in failures))
    if entry is None:
        return ProofResult("UNVERIFIED", None, ("no entry point found; nothing was run",))

    req_names: list[str] = []
    req_path = os.path.join(root_s, "requirements.txt")
    if os.path.isfile(req_path):
        src, _err = scan.read_source(root_s, "requirements.txt")
        if src is not None:
            req_names = sorted(requirements.declared_names(src.text))
    if req_names and wheelhouse is None:
        return ProofResult(
            "UNVERIFIED",
            None,
            ("dependencies cannot be installed offline without a wheelhouse: " + ", ".join(req_names),),
        )

    tmp = tempfile.mkdtemp(prefix="grimoire-verify-")
    try:
        work = os.path.join(tmp, "work")
        venv = os.path.join(tmp, "venv")
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        copy_tree(root_s, work)
        venv_cmd = [sys.executable, "-m", "venv"]
        if not req_names:
            venv_cmd.append("--without-pip")
        code, out, timed_out = _run(venv_cmd + [venv], tmp, _minimal_env(home, None), SETUP_TIMEOUT)
        if code != 0:
            return ProofResult("UNVERIFIED", code, ("virtual environment could not be created",) + _log_lines(out, tmp))
        python = os.path.join(venv, "bin", "python")
        env = _minimal_env(home, venv)
        if req_names:
            assert wheelhouse is not None
            wheels = str(Path(wheelhouse).resolve())
            code, out, timed_out = _run(
                [python, "-m", "pip", "install", "--no-index", "--find-links", wheels, "-r", "requirements.txt"],
                work,
                env,
                SETUP_TIMEOUT,
            )
            if code != 0:
                return ProofResult(
                    "UNVERIFIED",
                    code,
                    ("dependencies could not be installed offline from the wheelhouse",) + _log_lines(out, tmp),
                )
        code, out, timed_out = _run([python, entry], work, env, timeout)
        lines = _log_lines(out, tmp)
        if timed_out:
            return ProofResult("TIMED_OUT", None, lines + (f"killed after {timeout:g}s timeout",))
        return ProofResult("ALIVE" if code == 0 else "STILL_DEAD", code, lines)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
