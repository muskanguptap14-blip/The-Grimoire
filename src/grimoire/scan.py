"""Repository discovery, language and project detection, and safe file reading.

All file I/O of the analysis side lives here. Output is sorted, uses
repo-relative paths with ``/`` separators and contains no absolute paths.
"""

from __future__ import annotations

import io
import os
import tokenize
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .models import Finding, make_finding

IGNORED_DIRS = frozenset({".git", "venv", ".venv", "node_modules", "__pycache__", ".grimoire-backup"})

# Extension -> language. Only languages in ANALYZED_LANGUAGES have an analyzer.
LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".pl": "perl",
    ".sh": "shell",
}
ANALYZED_LANGUAGES = frozenset({"python"})

PYTHON_MANIFESTS = frozenset({"pyproject.toml", "setup.cfg"})


class PathEscapeError(ValueError):
    """Raised when a relative path would leave the repository root."""


@dataclass(frozen=True)
class ScannedFile:
    path: str
    kind: str  # python | requirements | python-manifest | node-manifest | source
    language: str  # "" when not a source file


@dataclass(frozen=True)
class ScanResult:
    files: tuple[ScannedFile, ...]
    languages: tuple[tuple[str, int], ...]
    project_types: tuple[str, ...]
    findings: tuple[Finding, ...]

    def paths(self, kind: str) -> tuple[str, ...]:
        return tuple(f.path for f in self.files if f.kind == kind)


@dataclass(frozen=True)
class SourceFile:
    text: str
    encoding: str


def detect_language(path: str) -> str:
    """Language of a source file by extension, or '' when unknown."""
    return LANGUAGE_BY_EXTENSION.get(PurePosixPath(path).suffix.lower(), "")


def classify_file(path: str) -> ScannedFile | None:
    name = PurePosixPath(path).name
    if name == "requirements.txt":
        return ScannedFile(path, "requirements", "")
    if name == "package.json":
        return ScannedFile(path, "node-manifest", "")
    if name in PYTHON_MANIFESTS:
        return ScannedFile(path, "python-manifest", "")
    language = detect_language(path)
    if language == "python":
        return ScannedFile(path, "python", "python")
    if language:
        return ScannedFile(path, "source", language)
    return None


def resolve_in_repo(root: str | os.PathLike[str], rel: str) -> Path:
    """Resolve ``rel`` under ``root``; reject traversal, absolute paths and escaping symlinks."""
    if not rel or "\x00" in rel:
        raise PathEscapeError(f"invalid relative path: {rel!r}")
    pure = PurePosixPath(rel.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts:
        raise PathEscapeError(f"path escapes repository: {rel!r}")
    root_real = Path(root).resolve()
    candidate = (root_real / pure).resolve()
    if candidate != root_real and root_real not in candidate.parents:
        raise PathEscapeError(f"path escapes repository: {rel!r}")
    return root_real / pure


def _escapes(root_real: Path, path: Path) -> bool:
    real = path.resolve()
    return real != root_real and root_real not in real.parents


def scan_repo(root: str | os.PathLike[str]) -> ScanResult:
    """Recursively scan ``root`` in sorted order and detect languages and project types."""
    root_path = Path(root)
    if not root_path.is_dir():
        finding = make_finding("INVALID_REPO", ".", 0, "repository path is not a directory")
        return ScanResult((), (), (), (finding,))
    root_real = root_path.resolve()
    files: list[ScannedFile] = []
    findings: list[Finding] = []
    for dirpath, dirnames, filenames in os.walk(root_real, followlinks=False):
        here = Path(dirpath)
        kept: list[str] = []
        for d in sorted(dirnames):
            if d in IGNORED_DIRS:
                continue
            full = here / d
            if full.is_symlink():
                if _escapes(root_real, full):
                    rel = full.relative_to(root_real).as_posix()
                    findings.append(
                        make_finding("SYMLINK_ESCAPE", rel, 0, "symlinked directory points outside the repository; skipped")
                    )
                continue
            kept.append(d)
        dirnames[:] = kept
        for name in sorted(filenames):
            full = here / name
            rel = full.relative_to(root_real).as_posix()
            if full.is_symlink() and _escapes(root_real, full):
                findings.append(
                    make_finding("SYMLINK_ESCAPE", rel, 0, "symlink points outside the repository; skipped")
                )
                continue
            scanned = classify_file(rel)
            if scanned is not None:
                files.append(scanned)
    files.sort(key=lambda f: f.path)
    counts: dict[str, int] = {}
    for f in files:
        if f.language:
            counts[f.language] = counts.get(f.language, 0) + 1
    project_types: set[str] = set()
    for f in files:
        if f.kind in ("python", "requirements", "python-manifest"):
            project_types.add("python")
        elif f.kind == "node-manifest":
            project_types.add("node")
    for lang in counts:
        if lang in ("javascript", "typescript") and "node" not in project_types:
            project_types.add("node")
    return ScanResult(
        files=tuple(files),
        languages=tuple(sorted(counts.items())),
        project_types=tuple(sorted(project_types)),
        findings=tuple(findings),
    )


def read_source(root: str | os.PathLike[str], rel: str) -> tuple[SourceFile | None, Finding | None]:
    """Read a text file honoring PEP 263 cookies. Failures become Findings, never exceptions."""
    try:
        path = resolve_in_repo(root, rel)
        data = path.read_bytes()
    except PathEscapeError as exc:
        return None, make_finding("UNREADABLE", rel, 0, str(exc))
    except OSError as exc:
        return None, make_finding("UNREADABLE", rel, 0, f"cannot read file: {exc.strerror or exc}")
    return decode_source(data, rel)


def decode_source(data: bytes, rel: str) -> tuple[SourceFile | None, Finding | None]:
    if b"\x00" in data:
        return None, make_finding("BAD_ENCODING", rel, 0, "file contains NUL bytes (binary content)")
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    except SyntaxError as exc:
        return None, make_finding("BAD_ENCODING", rel, 1, f"invalid encoding declaration: {exc.msg}")
    try:
        text = data.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        line = 0
        if isinstance(exc, UnicodeDecodeError):
            line = data.count(b"\n", 0, exc.start) + 1
        return None, make_finding("BAD_ENCODING", rel, line, f"cannot decode as {encoding}")
    return SourceFile(text, encoding), None
