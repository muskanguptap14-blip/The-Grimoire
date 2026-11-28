"""Rule NE_OPERATOR: wraps the lib2to3 fixer logic, with a stable rule ID."""

from __future__ import annotations

from lib2to3 import pytree
from lib2to3.fixes.fix_ne import FixNe

from ._fixers import run_fixer

RULE_ID = "NE_OPERATOR"


def apply(tree: pytree.Base) -> pytree.Base:
    return run_fixer(tree, FixNe)
