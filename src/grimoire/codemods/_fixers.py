"""Helpers shared by codemods: run a lib2to3 fixer over a CST."""

from __future__ import annotations

from .. import py2parse  # noqa: F401  (ensures warnings are suppressed before lib2to3 import)

from lib2to3 import pytree  # noqa: E402


def run_fixer(tree: pytree.Base, fixer_cls: type) -> pytree.Base:
    fixer = fixer_cls({}, [])
    fixer.start_tree(tree, "<grimoire>")
    accept = getattr(fixer, "_accept_type", None)
    for node in list(tree.post_order()):
        if accept is not None and node.type != accept:
            continue
        if node.parent is None and node is not tree:
            continue  # detached by an earlier replacement
        results = fixer.match(node)
        if results:
            new = fixer.transform(node, results)
            if new is not None and new is not node:
                node.replace(new)
    return tree
