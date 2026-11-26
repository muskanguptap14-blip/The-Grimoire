"""Rule STRING_PREFIX: ``ur"..."`` is invalid in Python 3; drop the ``u``."""

from __future__ import annotations

import re

from lib2to3 import pytree
from lib2to3.pgen2 import token

RULE_ID = "STRING_PREFIX"

_UR = re.compile(r"^[uU]([rR])(?=['\"])")


def apply(tree: pytree.Base) -> pytree.Base:
    for leaf in list(tree.leaves()):
        if leaf.type == token.STRING and _UR.match(leaf.value):
            leaf.value = _UR.sub(r"\1", leaf.value, count=1)
            leaf.changed()
    return tree
