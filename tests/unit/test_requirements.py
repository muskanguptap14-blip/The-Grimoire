import pytest

from grimoire import requirements as rq


def fix(text):
    return rq.fix_requirements(text)


def test_parse_render_roundtrip():
    text = "# c\n\nrequests>=2.0,<3  # why\n-r other.txt\n--index-url x\ngit+https://h/r.git#egg=x\nflask[async] ; python_version>'3'\nbad !!\n"
    assert rq.render(rq.parse(text)) == text


def test_kinds():
    kinds = [l.kind for l in rq.parse("# c\n\n-r a\nok==1\n!!\nx @ https://h/x.whl\n")]
    assert kinds == ["COMMENT", "BLANK", "OPTION", "REQUIREMENT", "MALFORMED", "OPTION"]


def test_rename_remove_dedupe_malformed():
    text = "PIL\ndistribute\nPillow\nrequests\n!!bad\nBeautifulSoup==3.2\n"
    out, findings = fix(text)
    assert out == "Pillow\nrequests\n# grimoire: malformed requirement commented out: !!bad\nbeautifulsoup4==3.2\n"
    assert sorted(f.rule_id for f in findings) == [
        "DUPLICATE_REQUIREMENT", "MALFORMED_REQUIREMENT", "REMOVED_PACKAGE", "RENAMED_PACKAGE", "RENAMED_PACKAGE",
    ]


@pytest.mark.parametrize(
    "line,expected",
    [
        ("numpy==1.8.0\n", "numpy>=1.23.2\n"),
        ("numpy==1.24.0\n", "numpy==1.24.0\n"),
        ("numpy>=1.0\n", "numpy>=1.0\n"),
        ("numpy<=1.9\n", "numpy>=1.23.2\n"),
        ("Django==1.4  # old\n", "Django>=4.1.3,<5  # old\n"),
        ("PIL==1.1.7\n", "Pillow>=9.3.0\n"),
        ("numpy\n", "numpy\n"),
    ],
)
def test_bad_pins(line, expected):
    assert fix(line)[0] == expected


def test_options_comments_order_preserved():
    text = "# top\n-r base.txt\nzzz\naaa\n--index-url u\n"
    assert fix(text)[0] == text


def test_idempotent():
    text = "PIL==1.1.7\ndistribute\nnumpy==1.8.0\nnumpy\n!!x\n"
    once, _ = fix(text)
    twice, findings = fix(once)
    assert once == twice and findings == ()


def test_crlf_preserved():
    assert fix("PIL\r\nrequests\r\n")[0] == "Pillow\r\nrequests\r\n"


def test_version_comparison():
    assert rq.is_bad_pin("==1.8", "1.23.2")
    assert not rq.is_bad_pin("==1.23.2", "1.23.2")
    assert not rq.is_bad_pin(">=1.0", "1.23.2")
    assert rq.is_bad_pin("~=1.8.0", "1.23.2")
    assert not rq.is_bad_pin("==2", "1.23.2")


def test_add_requirements_idempotent_sorted():
    out = rq.add_requirements("requests", ["numpy", "Requests", "six"])
    assert out == "requests\nnumpy\nsix\n"
    assert rq.add_requirements(out, ["numpy"]) == out


def test_packages_map_valid():
    table = rq.load_packages_map()
    assert set(table) == {"renames", "removed", "bad_pins", "import_names"}
    for k, v in table["renames"].items():
        assert k == rq.normalize(k) and v
        assert rq.normalize(v) not in table["renames"]
    assert len(table["removed"]) == len(set(table["removed"]))
    assert all(n == rq.normalize(n) for n in table["removed"])
    for k, v in table["bad_pins"].items():
        assert k == rq.normalize(k)
        assert v["replacement"] and not rq.is_bad_pin(v["replacement"], v["below"])
    removed = set(table["removed"])
    assert not removed & {rq.normalize(v) for v in table["renames"].values()}
