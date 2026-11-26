"""Rule DICT_METHODS: ``has_key`` becomes ``in``; ``iter*`` methods become view methods."""

from __future__ import annotations

from lib2to3 import pytree
from lib2to3.fixes.fix_has_key import FixHasKey
from lib2to3.pgen2 import token
from lib2to3.pygram import python_symbols as syms

from ._fixers import run_fixer

RULE_ID = "DICT_METHODS"

ITER_METHODS = {"iteritems": "items", "itervalues": "values", "iterkeys": "keys"}


def apply(tree: pytree.Base) -> pytree.Base:
    run_fixer(tree, FixHasKey)
    for leaf in list(tree.leaves()):
        if leaf.type != token.NAME or leaf.value not in ITER_METHODS:
            continue
        parent = leaf.parent
        if parent is None or parent.type != syms.trailer or parent.children[0].type != token.DOT:
            continue
        call = parent.next_sibling
        if call is None or call.type != syms.trailer or call.children[0].type != token.LPAR:
            continue
        leaf.value = ITER_METHODS[leaf.value]
        leaf.changed()
    return tree
