"""Dockerfile text generator. The text is never executed or built by Grimoire."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import PurePosixPath

from . import scan

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


DEFAULT_NODE_MAIN = "index.js"


def is_node_only(root: str | os.PathLike[str]) -> bool:
    """True for a root ``package.json`` and no Python source files."""
    manifest = os.path.join(root, "package.json")
    if not os.path.isfile(manifest) or os.path.islink(manifest):
        return False
    return not scan.scan_repo(root).paths("python")


def detect_node_main(root: str | os.PathLike[str]) -> str:
    """``main`` from the root package.json; ``index.js`` when missing, unreadable or unsafe."""
    try:
        with open(os.path.join(root, "package.json"), "rb") as fh:
            data = json.loads(fh.read().decode("utf-8-sig"))
    except (OSError, ValueError):
        return DEFAULT_NODE_MAIN
    main = data.get("main") if isinstance(data, dict) else None
    if not isinstance(main, str) or not main.strip() or "\x00" in main:
        return DEFAULT_NODE_MAIN
    pure = PurePosixPath(main.strip().replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() == ".":
        return DEFAULT_NODE_MAIN
    return pure.as_posix()


def generate_node_dockerfile(main: str) -> str:
    lines = [
        "FROM node:22-slim",
        "WORKDIR /app",
        "COPY package*.json ./",
        "RUN npm install --omit=dev",
        "COPY . .",
        "CMD [\"node\", %s]" % json.dumps(main),
    ]
    return "\n".join(lines) + "\n"


def generate_node_dockerignore() -> str:
    """Keeps a local node_modules and .git out of the image build context."""
    return "node_modules\n.git\n"
