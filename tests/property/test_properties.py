import ast

from hypothesis import given, strategies as st

from grimoire import codemods, py2parse, requirements
from grimoire.codemods import RULES, apply_all, apply_syntax_rules

from strategies import py2_modules, statements


def _as_module(stmt: str) -> str:
    return "import sys\n" + stmt + "\n"


@given(statements)
def test_roundtrip_is_lossless(stmt):
    src = _as_module(stmt)
    assert py2parse.render(py2parse.parse_py2(src)) == src


@given(py2_modules)
def test_patched_output_parses(module):
    result = apply_all(module, "m.py")
    assert not result.findings
    ast.parse(module if result.patch is None else result.patch.after)


@given(py2_modules)
def test_pipeline_idempotent(module):
    patch = apply_all(module, "m.py").patch
    first = module if patch is None else patch.after
    second = apply_all(first, "m.py")
    assert second.patch is None and not second.findings


@given(py2_modules)
def test_pipeline_deterministic(module):
    assert apply_all(module, "m.py") == apply_all(module, "m.py")


@given(statements, st.sampled_from(range(len(RULES))))
def test_each_rule_idempotent_and_parseable(stmt, idx):
    rule = RULES[idx]
    once, _ = apply_syntax_rules(_as_module(stmt), (rule,))
    twice, _ = apply_syntax_rules(once, (rule,))
    assert once == twice


req_lines = st.sampled_from(
    [
        "# comment\n", "\n", "requests>=2.0\n", "PIL==1.1.7\n", "distribute\n", "numpy==1.8.0\n",
        "Django==1.4\n", "-r other.txt\n", "--index-url https://x.invalid/simple\n", "six\n",
        "!!bad\n", "pillow\n", "flask[async]>=1 ; python_version>'3'  # why\n",
    ]
)
req_files = st.lists(req_lines, max_size=12).map("".join)


@given(req_files)
def test_requirements_roundtrip(text):
    assert requirements.render(requirements.parse(text)) == text


@given(req_files)
def test_requirements_fix_idempotent(text):
    once, _ = requirements.fix_requirements(text)
    twice, findings = requirements.fix_requirements(once)
    assert once == twice and findings == ()


@given(req_files)
def test_requirements_no_removed_names_and_order_kept(text):
    fixed, _ = requirements.fix_requirements(text)
    removed = {requirements.normalize(n) for n in requirements.load_packages_map()["removed"]}
    assert not removed & requirements.declared_names(fixed)
    # kept comment and option lines keep their relative order
    keep = [l for l in text.splitlines() if l.startswith(("#", "-"))]
    out = [l for l in fixed.splitlines() if l.startswith(("#", "-")) and "grimoire:" not in l]
    assert out == keep
