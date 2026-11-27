"""Deterministic unified diffs over FilePatch objects."""

from __future__ import annotations

import difflib
from collections.abc import Iterable

from .models import FilePatch


def _lines(text: str) -> list[str]:
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += "\n\\ No newline at end of file\n"
    return lines


def unified_diff(patches: Iterable[FilePatch]) -> str:
    """Unified diff sorted by repo-relative path, using a/ and b/ prefixes. No timestamps."""
    chunks: list[str] = []
    for patch in sorted(patches, key=lambda p: p.path):
        if patch.before == patch.after:
            continue
        chunks.extend(
            difflib.unified_diff(
                _lines(patch.before),
                _lines(patch.after),
                fromfile=f"a/{patch.path}",
                tofile=f"b/{patch.path}",
            )
        )
    return "".join(chunks)
