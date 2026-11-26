"""Rule BUILTINS: Python 2 builtins replaced by their Python 3 names."""

from __future__ import annotations

from lib2to3 import pytree
from lib2to3.pgen2 import token
from lib2to3.pygram import python_symbols as syms

RULE_ID = "BUILTINS"

REPLACEMENTS = {
    "xrange": "range",
    "raw_input": "input",
    "unicode": "str",
    "long": "int",
    "basestring": "str",
}


_FOR_TYPES = tuple(
    t for t in (getattr(syms, "for_stmt", None), getattr(syms, "comp_for", None), getattr(syms, "old_comp_for", None)) if t
)


def _names_in(node: pytree.Base) -> set[str]:
    return {leaf.value for leaf in node.leaves() if leaf.type == token.NAME}


def bound_names(tree: pytree.Base) -> set[str]:
    """Over-approximation of names the module binds itself (so they must not be rewritten)."""
    bound: set[str] = set()
    for node in tree.pre_order():
        if node.type in (syms.funcdef, syms.classdef):
            bound.add(node.children[1].value)
        elif node.type == syms.parameters:
            bound |= _names_in(node)
        elif node.type == syms.lambdef:
            bound |= _lambda_names(node)
        elif node.type == syms.expr_stmt:
            for child, nxt in zip(node.children, node.children[1:]):
                if nxt.type == token.EQUAL:
                    bound |= _names_in(child)
        elif node.type in _FOR_TYPES:
            for child in node.children[1:]:
                if child.type == token.NAME and child.value == "in":
                    break
                bound |= _names_in(child)
        elif node.type in (syms.import_as_name, syms.dotted_as_name):
            if len(node.children) == 3:
                bound.add(node.children[2].value)
    return bound


def _lambda_names(node: pytree.Base) -> set[str]:
    names: set[str] = set()
    for child in node.children[1:]:
        if child.type == token.COLON:
            break
        names |= _names_in(child)
    return names


def _is_replaceable(leaf: pytree.Leaf) -> bool:
    prev = leaf.prev_sibling
    if prev is not None and prev.type == token.DOT:
        return False  # attribute of another object, e.g. obj.xrange
    parent = leaf.parent
    if parent is not None and parent.type == syms.trailer and parent.children[0].type == token.DOT:
        return False
    if parent is not None and parent.type == syms.argument and leaf is parent.children[0]:
        nxt = leaf.next_sibling
        if nxt is not None and nxt.type == token.EQUAL:
            return False  # keyword argument name
    return True


def apply(tree: pytree.Base) -> pytree.Base:
    shadowed = bound_names(tree)
    for leaf in list(tree.leaves()):
        if leaf.type != token.NAME or leaf.value not in REPLACEMENTS:
            continue
        if leaf.value in shadowed or not _is_replaceable(leaf):
            continue
        leaf.value = REPLACEMENTS[leaf.value]
        leaf.changed()
    return tree
