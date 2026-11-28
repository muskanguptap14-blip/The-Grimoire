"""Rule EXCEPT_AS: wraps the lib2to3 fixer logic, with a stable rule ID."""

from __future__ import annotations

from lib2to3 import pytree
from lib2to3.fixes.fix_except import FixExcept

from ._fixers import run_fixer

RULE_ID = "EXCEPT_AS"


def apply(tree: pytree.Base) -> pytree.Base:
    return run_fixer(tree, FixExcept)
