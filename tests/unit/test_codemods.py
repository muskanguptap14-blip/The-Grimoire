import ast
import types

import pytest

from grimoire import codemods
from grimoire.codemods import apply_all, apply_syntax_rules


def conv(src, rule=None):
    rules = (rule,) if rule else codemods.RULES
    return apply_syntax_rules(src, rules)[0]


@pytest.mark.parametrize(
    "src,expected",
    [
        ('print "a"\n', 'print("a")\n'),
        ("print x, y\n", "print(x, y)\n"),
        ('print "a" % b\n', 'print("a" % b)\n'),
        ("print >>sys.stderr, x\n", "print(x, file=sys.stderr)\n"),
        ("print x,\n", "print(x, end=' ')\n"),
        ("print\n", "print()\n"),
        ("print('x')\n", "print('x')\n"),
        ("print(x + 1)\n", "print(x + 1)\n"),
    ],
)
def test_print_stmt(src, expected):
    assert conv(src, codemods.print_stmt) == expected


def test_except_as():
    assert conv("try:\n    pass\nexcept X, e:\n    pass\n") == "try:\n    pass\nexcept X as e:\n    pass\n"
    assert "except (A, B) as e:" in conv("try:\n    pass\nexcept (A, B), e:\n    pass\n")


def test_raise_stmt():
    assert conv('raise E, "m"\n') == 'raise E("m")\n'
    assert conv("raise E\n", codemods.raise_stmt) == "raise E\n"
    assert conv("raise\n", codemods.raise_stmt) == "raise\n"


def test_backticks_ne_exec_octal_prefix():
    assert conv("x = `y`\n", codemods.backticks) == "x = repr(y)\n"
    assert conv("if a <> b: pass\n", codemods.ne_operator) == "if a != b: pass\n"
    assert conv('exec "x = 1"\n', codemods.exec_stmt) == 'exec("x = 1")\n'
    assert conv("m = 0755\n", codemods.octal_literals) == "m = 0o755\n"
    assert conv("n = 10L\n", codemods.octal_literals) == "n = 10\n"
    assert conv('s = ur"x"\n', codemods.string_prefix) == 's = r"x"\n'
    assert conv('s = u"x"\n', codemods.string_prefix) == 's = u"x"\n'


def test_builtins_and_attribute_and_shadowing():
    src = "for i in xrange(3):\n    v = raw_input()\nok = isinstance(v, basestring) or unicode(v) or long(v)\n"
    out = conv(src, codemods.builtins)
    assert out == "for i in range(3):\n    v = input()\nok = isinstance(v, str) or str(v) or int(v)\n"
    assert conv("obj.xrange(3)\n", codemods.builtins) == "obj.xrange(3)\n"
    assert conv("f(unicode=1)\n", codemods.builtins) == "f(unicode=1)\n"
    shadow = "def unicode(x):\n    return x\nunicode(1)\n"
    assert conv(shadow, codemods.builtins) == shadow
    assert conv("def f(long):\n    return long\n", codemods.builtins) == "def f(long):\n    return long\n"


def test_dict_methods():
    out = conv("for k, v in d.iteritems():\n    pass\nx = d.has_key(k)\nd.itervalues()\nd.iterkeys()\n", codemods.dict_methods)
    assert out == "for k, v in d.items():\n    pass\nx = k in d\nd.values()\nd.keys()\n"


def test_comments_blank_lines_and_indentation_preserved():
    src = "# header\n\ndef f():\n    # note\n    print 'a'   # trailing\n\n\n    return 1\n"
    out = conv(src)
    assert out == "# header\n\ndef f():\n    # note\n    print('a')   # trailing\n\n\n    return 1\n"


def test_no_trailing_newline_and_crlf():
    assert conv('print "a"') == 'print("a")'
    assert conv('print "a"\r\nx = 1\r\n') == 'print("a")\r\nx = 1\r\n'


def test_apply_all_patch_and_idempotent():
    src = 'import urllib2\nprint "x"\nurllib2.urlopen("u")\n'
    first = apply_all(src, "a.py")
    assert first.patch.rules_applied == ("PRINT_STMT", "OUTDATED_IMPORT")
    ast.parse(first.patch.after)
    assert apply_all(first.patch.after, "a.py").patch is None


def test_apply_all_leaves_valid_py3_untouched():
    result = apply_all("x = 1\nprint(x)\n", "a.py")
    assert result.patch is None and result.findings == ()


def test_unparseable_left_alone():
    result = apply_all("def f(:\n", "bad.py")
    assert result.patch is None
    assert [f.rule_id for f in result.findings] == ["UNPARSEABLE"]


def test_forced_bad_rule_is_rejected_and_original_kept():
    bad = types.SimpleNamespace(RULE_ID="PRINT_STMT", apply=lambda tree: _break(tree))
    result = apply_all('print "x"\n', "a.py", rules=(bad,))
    assert result.patch is None
    assert [f.rule_id for f in result.findings] == ["PATCH_REJECTED"]


def _break(tree):
    from lib2to3.pytree import Leaf
    from lib2to3.pgen2 import token

    leaf = next(tree.leaves())
    leaf.replace(Leaf(token.NAME, "def ((("))
    return tree


def test_rule_order_is_fixed():
    assert [r.RULE_ID for r in codemods.RULES] == [
        "PRINT_STMT", "EXCEPT_AS", "RAISE_STMT", "BACKTICKS", "NE_OPERATOR", "EXEC_STMT",
        "OCTAL_LITERAL", "STRING_PREFIX", "BUILTINS", "DICT_METHODS",
    ]
