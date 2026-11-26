"""Rule PRINT_STMT: ``print`` statements become ``print()`` calls.

``print(...)`` written with a single parenthesized argument is treated as an
existing Python 3 style call and left untouched, which keeps the rule idempotent.
"""

from __future__ import annotations

from lib2to3 import pytree
from lib2to3.fixes.fix_print import FixPrint
from lib2to3.pgen2 import token
from lib2to3.pygram import python_symbols as syms

from ._fixers import run_fixer

RULE_ID = "PRINT_STMT"


class _FixPrint(FixPrint):
    def transform(self, node, results):  # type: ignore[no-untyped-def]
        if node.type == syms.print_stmt and len(node.children) == 2:
            arg = node.children[1]
            if (
                arg.type == syms.atom
                and arg.children[0].type == token.LPAR
                and arg.children[-1].type == token.RPAR
            ):
                return None
        return super().transform(node, results)


def apply(tree: pytree.Base) -> pytree.Base:
    return run_fixer(tree, _FixPrint)
