"""Dockerfile text generator. The text is never executed or built by Grimoire."""

from __future__ import annotations

import os
import tomllib
from pathlib import PurePosixPath

ENTRY_CANDIDATES = ("__main__.py", "main.py", "run.py", "app.py")


def _valid_entry(root: str | os.PathLike[str], entry: object) -> str | None:
    if not isinstance(entry, str) or not entry or "\x00" in entry:
        return None
    pure = PurePosixPath(entry.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or pure.suffix != ".py":
        return None
    full = os.path.join(root, *pure.parts)
    if os.path.islink(full) or not os.path.isfile(full):
        return None
    return pure.as_posix()


def detect_entry(root: str | os.PathLike[str]) -> str | None:
    """Entry point: grimoire.toml ``entry`` key first, then the fixed candidate order."""
    config = os.path.join(root, "grimoire.toml")
    if os.path.isfile(config) and not os.path.islink(config):
        try:
            with open(config, "rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        entry = _valid_entry(root, data.get("entry"))
        if entry:
            return entry
    for name in ENTRY_CANDIDATES:
        entry = _valid_entry(root, name)
        if entry:
            return entry
    return None


def generate_dockerfile(entry: str | None, has_requirements: bool) -> str:
    lines = ["FROM python:3.11-slim", "WORKDIR /app"]
    if has_requirements:
        lines += [
            "COPY requirements.txt .",
            "RUN pip install --no-cache-dir -r requirements.txt",
        ]
    lines.append("COPY . .")
    if entry:
        lines.append('CMD ["python", "%s"]' % entry.replace("\\", "\\\\").replace('"', '\\"'))
    else:
        lines.append("# No entry point was detected (__main__.py, main.py, run.py, app.py, grimoire.toml)")
        lines.append('CMD ["python"]')
    return "\n".join(lines) + "\n"
