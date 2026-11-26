import pytest

from grimoire import py2parse


@pytest.mark.parametrize(
    "src,expected",
    [
        ('print "x"\n', "PY2"),
        ("print('x')\n", "PY3"),
        ("x = 1\n", "PY3"),
        ("def f(:\n", "UNPARSEABLE"),
        ("except ValueError, e:\n", "UNPARSEABLE"),
        ("x = \x00\n", "UNPARSEABLE"),
        ("try:\n    pass\nexcept ValueError, e:\n    pass\n", "PY2"),
        ("", "PY3"),
    ],
)
def test_classify(src, expected):
    assert py2parse.classify(src) == expected


@pytest.mark.parametrize(
    "src",
    ['print "x"', 'print "x"\n', "x = 1\r\nprint x\r\n", "# c\n\nprint 1  # t\n", "if a:\n\tprint a\n"],
)
def test_roundtrip(src):
    assert py2parse.render(py2parse.parse_py2(src)) == src


def test_garbage_raises():
    with pytest.raises(py2parse.Py2ParseError):
        py2parse.parse_py2("def f(:\n")


def test_py3_syntax_error_reports_line():
    assert py2parse.python3_syntax_error("x = 1\ndef f(:\n")[0] == 2
    assert py2parse.python3_syntax_error("x = 1\n") is None


def test_mixed_print_function_and_py2_keyword():
    src = 'print("a", sep="")\nraise E, "m"\n'
    assert py2parse.classify(src) == "PY2"
