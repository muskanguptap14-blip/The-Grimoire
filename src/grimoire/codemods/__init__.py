"""Codemod pipeline: fixed rule order, whole-file reject path."""

from __future__ import annotations

import ast
from types import ModuleType
from typing import Sequence

from .. import py2parse
from ..models import FilePatch, PatchResult, make_finding
from . import (
    backticks,
    builtins,
    dict_methods,
    except_as,
    exec_stmt,
    ne_operator,
    octal_literals,
    print_stmt,
    raise_stmt,
    string_prefix,
)

# Fixed order. Changing it changes output; tests re-run the pipeline to prove idempotency.
RULES: tuple[ModuleType, ...] = (
    print_stmt,
    except_as,
    raise_stmt,
    backticks,
    ne_operator,
    exec_stmt,
    octal_literals,
    string_prefix,
    builtins,
    dict_methods,
)


def apply_syntax_rules(source: str, rules: Sequence[ModuleType] = RULES) -> tuple[str, tuple[str, ...]]:
    """Apply Python 2 codemods in order to one source string. Raises Py2ParseError."""
    tree = py2parse.parse_py2(source)
    applied: list[str] = []
    for rule in rules:
        before = py2parse.render(tree)
        tree = rule.apply(tree)
        if py2parse.render(tree) != before:
            applied.append(rule.RULE_ID)
    return py2parse.render(tree), tuple(applied)


def apply_all(
    source: str,
    path: str = "<source>",
    rules: Sequence[ModuleType] = RULES,
    imports: bool = True,
) -> PatchResult:
    """Run codemods (Python 2 files) and the imports rewriter on one file.

    Returns a PatchResult. ``patch`` is None when nothing changed, or when the
    result is rejected (PATCH_REJECTED, original kept) or the file is UNPARSEABLE.
    """
    kind = py2parse.classify(source)
    if kind == py2parse.UNPARSEABLE:
        line, msg = py2parse.python3_syntax_error(source) or (0, "invalid syntax")
        finding = make_finding("UNPARSEABLE", path, line, f"parses under neither grammar: {msg}")
        return PatchResult(None, (finding,))

    current = source
    applied: list[str] = []
    if kind == py2parse.PY2:
        current, applied_rules = apply_syntax_rules(source, rules)
        applied.extend(applied_rules)
    if imports:
        from .. import imports as imports_mod

        try:
            tree = py2parse.parse_py2(current) if kind == py2parse.PY2 else py2parse.parse_py3_cst(current)
        except py2parse.Py2ParseError:
            tree = None
        if tree is not None:
            before = py2parse.render(tree)
            tree = imports_mod.apply(tree)
            after = py2parse.render(tree)
            if after != before:
                applied.append(imports_mod.RULE_ID)
                current = after
    if current == source:
        return PatchResult(None, ())
    try:
        ast.parse(current)
    except (SyntaxError, ValueError, RecursionError) as exc:
        line = getattr(exc, "lineno", 0) or 0
        finding = make_finding(
            "PATCH_REJECTED", path, line, f"patched output fails ast.parse ({exc}); original kept"
        )
        return PatchResult(None, (finding,))
    return PatchResult(FilePatch(path, source, current, tuple(applied)), ())
