"""Hypothesis strategies generating valid Python 2 statements and small modules."""

from __future__ import annotations

from hypothesis import strategies as st

names = st.sampled_from(["a", "b", "x", "y", "total", "name", "items"])
exprs = st.one_of(
    names,
    st.integers(0, 99).map(str),
    st.sampled_from(['"s"', "'t'", "a + 1", "x * 2", "a % b", '"v=%d" % x']),
)

print_stmts = st.one_of(
    st.just("print"),
    exprs.map(lambda e: f"print {e}"),
    st.tuples(exprs, exprs).map(lambda t: f"print {t[0]}, {t[1]}"),
    exprs.map(lambda e: f"print {e},"),
    exprs.map(lambda e: f"print >>sys.stderr, {e}"),
)
raise_stmts = st.one_of(
    st.just("raise"),
    st.just("raise ValueError"),
    st.sampled_from(['raise ValueError, "m"', 'raise KeyError, x']),
)
except_blocks = st.sampled_from(
    [
        "try:\n    pass\nexcept ValueError, e:\n    pass",
        "try:\n    pass\nexcept (A, B), err:\n    pass",
        "try:\n    pass\nexcept ValueError:\n    pass",
    ]
)
builtin_stmts = st.sampled_from(
    [
        "for i in xrange(10):\n    pass",
        "v = raw_input()",
        "ok = isinstance(x, basestring)",
        "s = unicode(x)",
        "n = long(x)",
        "obj.xrange(3)",
    ]
)
dict_stmts = st.sampled_from(
    [
        "for k, v in d.iteritems():\n    pass",
        "vals = d.itervalues()",
        "keys = d.iterkeys()",
        "r = d.has_key(k)",
    ]
)
misc_stmts = st.sampled_from(
    [
        "r = `x`",
        "if a <> b:\n    pass",
        'exec "x = 1"',
        "m = 0755",
        "big = 10L",
        's = ur"raw"',
    ]
)

statements = st.one_of(print_stmts, raise_stmts, except_blocks, builtin_stmts, dict_stmts, misc_stmts)

py2_modules = st.lists(statements, min_size=1, max_size=6).map(
    lambda stmts: "import sys\n" + "\n".join(stmts) + "\n"
)
