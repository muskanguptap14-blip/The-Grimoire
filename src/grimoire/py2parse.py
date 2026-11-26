"""Python 2 / 3 parsing facade. All lib2to3 use is isolated in this module."""

from __future__ import annotations

import ast
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from lib2to3 import pygram, pytree
    from lib2to3.pgen2 import driver

PY3 = "PY3"
PY2 = "PY2"
UNPARSEABLE = "UNPARSEABLE"

_PARSE_ERRORS = (SyntaxError, ValueError, RecursionError, MemoryError)

symbols = pygram.python_symbols
Leaf = pytree.Leaf
Node = pytree.Node


class Py2ParseError(Exception):
    """Source parses under neither the Python 2 grammar nor the Python 3 CST grammar."""


def _python3_parses(source: str) -> bool:
    try:
        ast.parse(source)
    except _PARSE_ERRORS:
        return False
    return True


def _cst(source: str, grammar: object) -> pytree.Base:
    added = not source.endswith("\n")
    text = source + "\n" if added else source
    drv = driver.Driver(grammar, convert=pytree.convert)
    tree = drv.parse_string(text)
    tree._grimoire_added_newline = added  # type: ignore[attr-defined]
    return tree


def parse_py2(source: str) -> pytree.Base:
    """Parse as Python 2 into a lossless CST. Raises Py2ParseError on failure."""
    last: Exception | None = None
    # print-statement grammar first; fall back for files mixing print() with keywords.
    for grammar in (pygram.python_grammar, pygram.python_grammar_no_print_statement):
        try:
            return _cst(source, grammar)
        except Exception as exc:  # lib2to3 raises ParseError, TokenError, IndentationError...
            last = exc
    raise Py2ParseError(str(last))


def parse_py3_cst(source: str) -> pytree.Base:
    """Parse Python 3 source into a lossless CST (no print statement)."""
    try:
        return _cst(source, pygram.python_grammar_no_print_statement)
    except Exception as exc:
        raise Py2ParseError(str(exc)) from exc


def render(tree: pytree.Base) -> str:
    text = str(tree)
    if getattr(tree, "_grimoire_added_newline", False) and text.endswith("\n"):
        text = text[:-1]
    return text


def classify(source: str) -> str:
    """PY3 if ast.parse accepts it, PY2 if only the Python 2 grammar does, else UNPARSEABLE."""
    if _python3_parses(source):
        return PY3
    try:
        parse_py2(source)
    except Py2ParseError:
        return UNPARSEABLE
    return PY2


def python3_syntax_error(source: str) -> tuple[int, str] | None:
    """(line, message) of the Python 3 syntax error, or None when the source parses."""
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return (exc.lineno or 0, exc.msg)
    except (ValueError, RecursionError, MemoryError) as exc:
        return (0, str(exc))
    return None
