"""Outdated import detection (AST) and rewriting (CST) driven by data/imports_map.json."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from . import py2parse
from .py2parse import Leaf, Node, symbols as syms

from lib2to3.pgen2 import token  # noqa: E402

RULE_ID = "OUTDATED_IMPORT"


@lru_cache(maxsize=1)
def load_imports_map() -> dict[str, dict]:
    text = resources.files("grimoire").joinpath("data/imports_map.json").read_text(encoding="utf-8")
    return json.loads(text)


# --------------------------------------------------------------------------- AST side


@dataclass(frozen=True)
class ImportRef:
    module: str  # dotted module, "" for ``from . import x``
    level: int  # leading dots
    names: tuple[str, ...]
    line: int
    guarded: bool  # inside ``try`` whose handlers catch ImportError


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names: list[str] = []
    for node in ast.walk(handler.type):
        if isinstance(node, ast.Name):
            names.append(node.id)
    return any(n in ("ImportError", "ModuleNotFoundError", "Exception") for n in names)


def collect_imports(tree: ast.AST) -> list[ImportRef]:
    """All import statements in the tree, in source order."""
    refs: list[ImportRef] = []

    def visit(node: ast.AST, guarded: bool) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(ImportRef(alias.name, 0, (), node.lineno, guarded))
        elif isinstance(node, ast.ImportFrom):
            refs.append(
                ImportRef(node.module or "", node.level, tuple(a.name for a in node.names), node.lineno, guarded)
            )
        if isinstance(node, ast.Try):
            catches = any(_catches_import_error(h) for h in node.handlers)
            for child in node.body:
                visit(child, guarded or catches)
            for part in (node.handlers, node.orelse, node.finalbody):
                for child in part:
                    visit(child, guarded)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, guarded)

    visit(tree, False)
    return sorted(refs, key=lambda r: (r.line, r.module))


def lookup(module: str) -> dict | None:
    """Mapping entry for a module name (exact match), or None."""
    return load_imports_map().get(module)


# --------------------------------------------------------------------------- CST side


def _dotted_text(node: object) -> str:
    return "".join(leaf.value for leaf in node.leaves())  # type: ignore[attr-defined]


def _attr_target(entry: dict, attr: str, new: str) -> tuple[str, str]:
    """(module, name) a use of ``old.attr`` maps to."""
    target = entry["attrs"].get(attr)
    if target is None:
        return new, attr
    module, _, name = target.rpartition(".")
    return module, name


def _find_uses(tree: object, bound: str) -> list[tuple[Leaf, Leaf]]:
    """(head NAME leaf, attribute NAME leaf) for each ``bound.attr`` expression."""
    uses: list[tuple[Leaf, Leaf]] = []
    for node in tree.pre_order():  # type: ignore[attr-defined]
        if node.type != syms.power or len(node.children) < 2:
            continue
        head, trailer = node.children[0], node.children[1]
        if (
            head.type == token.NAME
            and head.value == bound
            and trailer.type == syms.trailer
            and len(trailer.children) == 2
            and trailer.children[0].type == token.DOT
            and trailer.children[1].type == token.NAME
        ):
            uses.append((head, trailer.children[1]))
    return uses


def _set_value(leaf: Leaf, value: str) -> None:
    if leaf.value != value:
        leaf.value = value
        leaf.changed()


def _rewrite_uses(tree: object, bound: str, entry: dict, alias: str | None) -> list[str]:
    """Rewrite ``bound.attr`` uses; return extra modules that must be imported."""
    new = entry["new"]
    extras: list[str] = []
    for head, attr in _find_uses(tree, bound):
        module, name = _attr_target(entry, attr.value, new)
        if module == new:
            _set_value(head, alias or new)
        else:
            _set_value(head, module)
            if module not in extras:
                extras.append(module)
        _set_value(attr, name)
    return extras


def _import_items(node: Node) -> list[tuple[str, str | None]] | None:
    """Items of an ``import_name`` node as (dotted module, alias)."""
    spec = node.children[1]
    parts = spec.children[::2] if spec.type == syms.dotted_as_names else [spec]
    items: list[tuple[str, str | None]] = []
    for part in parts:
        if part.type == syms.dotted_as_name:
            items.append((_dotted_text(part.children[0]), part.children[2].value))
        elif part.type in (syms.dotted_name, token.NAME):
            items.append((_dotted_text(part), None))
        else:
            return None
    return items


def _rewrite_import_name(tree: object, node: Node) -> None:
    items = _import_items(node)
    if items is None or not any(m in load_imports_map() for m, _ in items):
        return
    rendered: list[str] = []
    for module, alias in items:
        entry = load_imports_map().get(module)
        if entry is None:
            rendered.append(module if alias is None else f"{module} as {alias}")
            continue
        new = entry["new"]
        extras = _rewrite_uses(tree, alias or module, entry, alias)
        if alias is None or alias == new:
            rendered.append(new)
        else:
            rendered.append(f"{new} as {alias}")
        rendered.extend(e for e in extras if e not in rendered)
    spec = node.children[1]
    replacement = Leaf(token.NAME, ", ".join(rendered), prefix=spec.prefix)
    spec.replace(replacement)


def _module_node(node: Node) -> object | None:
    """The module part of ``from X import ...`` (None for relative imports)."""
    mod = node.children[1]
    if mod.type in (token.NAME, syms.dotted_name):
        return mod
    return None


def _imported_names(node: Node) -> list[tuple[str, str | None]] | None:
    tail = node.children[3:]
    if len(tail) == 1 and tail[0].type == token.STAR:
        return [("*", None)]
    spec = tail[1] if tail and tail[0].type == token.LPAR else tail[0] if tail else None
    if spec is None:
        return None
    parts = spec.children[::2] if spec.type == syms.import_as_names else [spec]
    names: list[tuple[str, str | None]] = []
    for part in parts:
        if part.type == syms.import_as_name:
            names.append((part.children[0].value, part.children[2].value))
        elif part.type == token.NAME:
            names.append((part.value, None))
        else:
            return None
    return names


def _rewrite_import_from(node: Node) -> None:
    mod = _module_node(node)
    if mod is None:
        return
    module = _dotted_text(mod)
    entry = load_imports_map().get(module)
    if entry is None:
        return
    names = _imported_names(node)
    if names is None:
        return
    new = entry["new"]
    groups: dict[str, list[str]] = {}
    for name, alias in names:
        if name == "*":
            groups.setdefault(new, []).append("*")
            continue
        target_module, target_name = _attr_target(entry, name, new)
        local = alias or name
        text = target_name if target_name == local else f"{target_name} as {local}"
        groups.setdefault(target_module, []).append(text)
    if list(groups) == [new] and all(
        _attr_target(entry, n, new)[1] == n for n, _ in names if n != "*"
    ):
        mod.replace(Leaf(token.NAME, new, prefix=mod.prefix))  # fast path: module name only
        return
    statements = [f"from {m} import {', '.join(parts)}" for m, parts in groups.items()]
    first = node.children[0]
    text = "; ".join(statements)
    new_leaf = Leaf(token.NAME, text, prefix=first.prefix)
    for child in list(node.children):
        child.remove()
    node.append_child(new_leaf)


def apply(tree: object) -> object:
    """Rewrite mapped imports and their attribute uses in a CST (Python 3 syntax)."""
    for node in list(tree.pre_order()):  # type: ignore[attr-defined]
        if node.type == syms.import_name:
            _rewrite_import_name(tree, node)
        elif node.type == syms.import_from:
            _rewrite_import_from(node)
    return tree
