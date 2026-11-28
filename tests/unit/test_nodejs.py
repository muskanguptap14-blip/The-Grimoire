import json
import shutil
from pathlib import Path

import pytest

from grimoire import autopsy, cli, nodejs, revive
from grimoire.models import RULE_META

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "node-legacy"


def fix(text):
    return nodejs.fix_manifest(text)


def rule_ids(findings):
    return sorted(f.rule_id for f in findings)


def copy_fixture(tmp_path):
    dst = tmp_path / "node-legacy"
    shutil.copytree(FIXTURE, dst)
    return dst


# --------------------------------------------------------------------------- table


def test_table_shape_and_no_duplicate_keys():
    def no_dupes(pairs):
        keys = [k for k, _ in pairs]
        assert len(keys) == len(set(keys)), keys
        return dict(pairs)

    text = (Path(nodejs.__file__).parent / "data" / "node_map.json").read_text(encoding="utf-8")
    table = json.loads(text, object_pairs_hook=no_dupes)
    assert set(table) == {"renames", "deprecated", "bad_ranges", "engines_node"}
    for name, entry in table["renames"].items():
        assert name and entry["new"] and entry["range"] and name != entry["new"]
        assert nodejs.is_registry_range(entry["range"])
    assert all(table["deprecated"].values())
    assert not set(table["renames"]) & set(table["deprecated"])
    assert not set(table["renames"]) & set(table["bad_ranges"])


def test_replacements_are_never_themselves_flagged():
    """A replacement that matched its own rule would break idempotence."""
    table = nodejs.load_node_map()
    for name, rule in table["bad_ranges"].items():
        assert not nodejs.is_outdated(rule["replacement"], rule["below"]), name
    engines = table["engines_node"]
    assert not nodejs.is_outdated(engines["replacement"], engines["below"])


def test_new_rules_are_registered():
    for rule_id in ("NODE_RENAMED_PACKAGE", "NODE_BAD_RANGE", "NODE_DEPRECATED_PACKAGE", "NODE_ENGINE_OUTDATED"):
        assert rule_id in RULE_META


# --------------------------------------------------------------------------- ranges


@pytest.mark.parametrize(
    "spec,bound",
    [
        ("^1.2.3", (2, 0, 0)),
        ("^1.2", (2, 0, 0)),
        ("^0.2.3", (0, 3, 0)),
        ("^0.0.3", (0, 0, 4)),
        ("^0.0", (0, 1, 0)),
        ("^0", (1, 0, 0)),
        ("~1.2.3", (1, 3, 0)),
        ("~1", (2, 0, 0)),
        ("1.x", (2, 0, 0)),
        ("1.2.x", (1, 3, 0)),
        ("0.10.x", (0, 11, 0)),
        ("1.2.3", (1, 2, 4)),
        ("=1.2.3", (1, 2, 4)),
        ("v1.2.3", (1, 2, 4)),
        ("<2", (2, 0, 0)),
        ("<=2.1", (2, 2, 0)),
        ("<=14", (15, 0, 0)),
        (">=1.0.0 <3", (3, 0, 0)),
        (">= 1.0.0 < 3", (3, 0, 0)),
        ("^1.0.0 || ^2.0.0", (3, 0, 0)),
        ("1.2.3-beta.1", (1, 2, 4)),
        # unbounded or not plain semver: never flagged
        ("*", None),
        ("x", None),
        ("", None),
        (">=1.0.0", None),
        (">0.1", None),
        ("^1.0.0 || >=3", None),
        ("latest", None),
        ("next", None),
        ("git+https://example.com/x.git", None),
        ("file:../x", None),
        ("npm:pug@^3.0.0", None),
        ("workspace:*", None),
        ("1.2.3 - 2.3.4", None),
        ("^1.0.0 || latest", None),
    ],
)
def test_upper_bound(spec, bound):
    assert nodejs.upper_bound(spec) == bound


@pytest.mark.parametrize(
    "spec,below,expected",
    [
        ("^3.10.1", "4.17.21", True),
        ("4.17.20", "4.17.21", True),
        ("4.17.21", "4.17.21", False),
        ("^4.17.0", "4.17.21", False),
        ("~4.17.0", "4.17.21", False),
        ("^4.0.0 || ^3.0.0", "4.17.21", False),
        (">=1.0.0", "4.17.21", False),
        ("latest", "4.17.21", False),
        ("^16", "18.0.0", True),
        ("^18", "18.0.0", False),
        ("<=14", "18.0.0", True),
        ("<19", "18.0.0", False),
    ],
)
def test_is_outdated(spec, below, expected):
    assert nodejs.is_outdated(spec, below) is expected


@pytest.mark.parametrize(
    "spec,expected",
    [("^1.2.3", True), ("*", True), ("1.x", True), (">=1 <3", True), ("latest", False), ("npm:a@1", False),
     ("git+https://h/r.git", False), ("1.2.3 - 2.0.0", False), ("", False)],
)
def test_is_registry_range(spec, expected):
    assert nodejs.is_registry_range(spec) is expected


# --------------------------------------------------------------------------- fixer


def test_fixture_exact_output_and_findings():
    original = (FIXTURE / "package.json").read_text(encoding="utf-8")
    out, findings = fix(original)
    expected = (
        original.replace('"node": "0.10.x"', '"node": ">=18"')
        .replace('"jade": "~1.11.0"', '"jade": "npm:pug@^3.0.2"')
        .replace('"lodash": "^3.10.1"', '"lodash": "^4.17.21"')
        .replace('"node-uuid": "1.4.8"', '"node-uuid": "npm:uuid@^9.0.1"')
        .replace('"coffee-script": "1.12.7"', '"coffee-script": "npm:coffeescript@^2.7.0"')
        .replace('"fsevents": "^1.2.13"', '"fsevents": "^2.3.2"')
    )
    assert out == expected
    assert rule_ids(findings) == [
        "NODE_BAD_RANGE", "NODE_BAD_RANGE", "NODE_DEPRECATED_PACKAGE", "NODE_DEPRECATED_PACKAGE",
        "NODE_ENGINE_OUTDATED", "NODE_RENAMED_PACKAGE", "NODE_RENAMED_PACKAGE", "NODE_RENAMED_PACKAGE",
    ]
    by_rule = {(f.rule_id, f.reason.split()[0].split("@")[0]): f for f in findings}
    assert by_rule[("NODE_ENGINE_OUTDATED", "engines.node")].line == 11
    assert by_rule[("NODE_RENAMED_PACKAGE", "jade")].line == 14
    assert by_rule[("NODE_DEPRECATED_PACKAGE", "request")].repair_class == "MANUAL"
    assert by_rule[("NODE_BAD_RANGE", "fsevents")].line == 25


def test_key_order_formatting_and_untouched_values_preserved():
    original = (FIXTURE / "package.json").read_text(encoding="utf-8")
    out, _ = fix(original)
    before, after = json.loads(original), json.loads(out)
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        assert list(after[section]) == list(before[section])
    assert list(after) == list(before)
    assert '"files": ["index.js", "lib"]' in out  # compact array layout kept
    assert '    "name": "ember-ledger"' in out  # 4-space indent kept
    assert after["dependencies"]["express"] == before["dependencies"]["express"]
    assert after["dependencies"]["request"] == before["dependencies"]["request"]  # deprecated: unchanged


def test_idempotent_on_fixture():
    original = (FIXTURE / "package.json").read_text(encoding="utf-8")
    once, _ = fix(original)
    twice, findings = fix(once)
    assert once == twice
    assert rule_ids(findings) == ["NODE_DEPRECATED_PACKAGE", "NODE_DEPRECATED_PACKAGE"]  # manual only


def test_clean_manifest_is_returned_byte_for_byte():
    text = '{"name":"a",\n\t"dependencies": {"express": "^4.18.2"},\r\n "engines": {"node": ">=18"}}'
    assert fix(text) == (text, ())


def test_minified_crlf_and_tab_layouts_survive_edits():
    minified = '{"dependencies":{"node-uuid":"1.0.0"},"engines":{"node":"0.10.x"}}'
    assert fix(minified)[0] == '{"dependencies":{"node-uuid":"npm:uuid@^9.0.1"},"engines":{"node":">=18"}}'
    crlf = '{\r\n  "dependencies": {\r\n    "jade": "*"\r\n  }\r\n}\r\n'
    assert fix(crlf)[0] == '{\r\n  "dependencies": {\r\n    "jade": "npm:pug@^3.0.2"\r\n  }\r\n}\r\n'
    tabs = '{\n\t"devDependencies": {\n\t\t"lodash": "3.0.0"\n\t}\n}'
    assert fix(tabs)[0] == '{\n\t"devDependencies": {\n\t\t"lodash": "^4.17.21"\n\t}\n}'


def test_other_strings_and_escapes_are_untouched():
    text = '{"description": "caf\\u00e9 \\"jade\\" \\/ x", "dependencies": {"jade": "1.0.0"}}'
    out, _ = fix(text)
    assert out == text.replace('"1.0.0"', '"npm:pug@^3.0.2"')


def test_same_package_in_two_sections_is_found_in_each():
    text = '{\n"dependencies": {"lodash": "^3.0.0"},\n"devDependencies": {"lodash": "^3.0.0"}\n}'
    out, findings = fix(text)
    assert out.count("^4.17.21") == 2
    assert [f.line for f in findings] == [2, 3]


def test_non_registry_specs_and_existing_aliases_are_left_alone():
    deps = {
        "jade": "git+https://example.com/jade.git",
        "node-uuid": "npm:uuid@^9.0.1",
        "lodash": "file:../lodash",
        "request": "latest",
    }
    text = json.dumps({"dependencies": deps}, indent=2)
    out, findings = fix(text)
    assert out == text
    assert rule_ids(findings) == ["NODE_DEPRECATED_PACKAGE"]  # 'latest' is still the deprecated package


def test_peer_dependencies_are_reported_not_rewritten():
    text = json.dumps({"peerDependencies": {"request": "^2.0.0", "jade": "1.0.0", "lodash": "^3.0.0"}})
    out, findings = fix(text)
    assert out == text
    assert rule_ids(findings) == ["NODE_DEPRECATED_PACKAGE"]


def test_engines_not_a_string_or_not_outdated_is_ignored():
    for engines in ({"node": 14}, {"node": ">=18"}, {"npm": "^3"}, {"node": "*"}, [], "x", None):
        text = json.dumps({"engines": engines})
        assert fix(text) == (text, ())


@pytest.mark.parametrize(
    "text,line",
    [
        ("", 1),
        ("{", 1),
        ('{"a": 1,}', 1),
        ('{\n  "a": 1,\n  // comment\n}', 3),
        ("{'a': 1}", 1),
        ('{"a": NaN}', 1),
        ("[]", 1),
        ('"text"', 1),
        ("null", 1),
    ],
)
def test_invalid_manifest_is_a_finding_and_changes_nothing(text, line):
    out, findings = fix(text)
    assert out == text
    assert rule_ids(findings) == ["INVALID_MANIFEST"]
    assert findings[0].line == line and findings[0].repair_class == "MANUAL"


def test_deeply_nested_json_does_not_crash():
    text = "[" * 5000 + "]" * 5000
    out, findings = fix(text)
    assert out == text and rule_ids(findings) == ["INVALID_MANIFEST"]


def test_reserialize_fallback_keeps_indent_and_line_endings():
    data = {"a": {"b": 1}}
    assert nodejs._reserialize('{\n\t"a": 1\n}\n', data) == '{\n\t"a": {\n\t\t"b": 1\n\t}\n}\n'
    assert nodejs._reserialize('{\r\n  "a": 1\r\n}', data) == '{\r\n  "a": {\r\n    "b": 1\r\n  }\r\n}\r\n'


# --------------------------------------------------------------------------- autopsy and revive


def test_autopsy_without_node_flag_still_reports_unsupported(tmp_path):
    repo = copy_fixture(tmp_path)
    report = autopsy.autopsy(repo)
    assert {f.rule_id for f in report.findings} == {"UNSUPPORTED_LANGUAGE", "UNSUPPORTED_MANIFEST"}
    assert ("package.json", "UNSUPPORTED", 1) in report.coverage


def test_autopsy_with_node_flag_analyzes_the_manifest(tmp_path):
    repo = copy_fixture(tmp_path)
    report = autopsy.autopsy(repo, node=True)
    ids = {f.rule_id for f in report.findings}
    assert "UNSUPPORTED_MANIFEST" not in ids and "NODE_BAD_RANGE" in ids
    assert ("package.json", "ANALYZED", 1) in report.coverage
    assert ("javascript", "UNSUPPORTED", 1) in report.coverage  # JS sources are still unchecked
    assert dict(report.cause_of_death) == {"DEPENDENCY": 7, "MANIFEST": 1}


def test_autopsy_reports_invalid_and_unreadable_manifests(tmp_path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    report = autopsy.autopsy(tmp_path, node=True)
    assert [f.rule_id for f in report.findings] == ["INVALID_MANIFEST"]
    assert report.cause_of_death == (("MANIFEST", 1),)
    (tmp_path / "package.json").write_bytes(b'{"a": "\xff"}')
    assert [f.rule_id for f in autopsy.autopsy(tmp_path, node=True).findings] == ["BAD_ENCODING"]


def test_revive_repairs_manifest_and_never_touches_the_source_or_js(tmp_path):
    repo = copy_fixture(tmp_path)
    snapshot = {p.name: p.read_bytes() for p in repo.iterdir()}
    report = revive.revive(repo, node=True)
    assert {p: (repo / p).read_bytes() for p in snapshot} == snapshot  # source repo untouched
    assert [p.path for p in report.patches] == ["package.json"]
    assert report.patches[0].rules_applied == ("NODE_BAD_RANGE", "NODE_ENGINE_OUTDATED", "NODE_RENAMED_PACKAGE")
    assert "a/index.js" not in report.diff and "b/index.js" not in report.diff  # no JS file diff
    assert [f.rule_id for f in report.findings if f.severity != "INFO"] == ["NODE_DEPRECATED_PACKAGE"] * 2
    names = {name: status for name, status, _ in report.validation}
    assert names["all package.json files parse"] == "PASS"
    assert names["no unresolved findings"] == "FAIL"  # two manual findings remain
    assert len(report.before_findings) > len(report.findings)


def test_revive_without_node_flag_changes_nothing(tmp_path):
    report = revive.revive(copy_fixture(tmp_path))
    assert report.patches == () and report.diff == ""
    assert {n for n, _s, _d in report.validation} == {"all Python files parse", "no unresolved findings"}


def test_revive_is_deterministic_and_idempotent_on_its_output(tmp_path):
    repo = copy_fixture(tmp_path)
    assert revive.revive(repo, node=True) == revive.revive(repo, node=True)
    out = tmp_path / "revived"
    revive.revive(repo, out, node=True)
    again = revive.revive(out, node=True)
    assert again.patches == ()
    assert (out / ".grimoire-backup" / "package.json").read_bytes() == (FIXTURE / "package.json").read_bytes()
    assert (out / "index.js").read_bytes() == (FIXTURE / "index.js").read_bytes()


def test_node_only_repo_cannot_be_proven(tmp_path):
    report = revive.revive(copy_fixture(tmp_path), prove=True, node=True)
    assert report.proof.status == "STILL_DEAD"  # manual findings remain, nothing was run
    (tmp_path / "clean").mkdir()
    (tmp_path / "clean" / "package.json").write_text('{"name": "x"}\n', encoding="utf-8")
    assert revive.revive(tmp_path / "clean", prove=True, node=True).proof.status == "UNVERIFIED"


# --------------------------------------------------------------------------- CLI


def test_cli_node_flag(tmp_path, capsys):
    repo = copy_fixture(tmp_path)
    assert cli.main(["autopsy", str(repo)]) == 0
    assert "UNSUPPORTED_MANIFEST" in capsys.readouterr().out
    assert cli.main(["autopsy", str(repo), "--node"]) == 0
    out = capsys.readouterr().out
    assert "NODE_RENAMED_PACKAGE" in out and "package.json: ANALYZED" in out
    cli.main(["revive", str(repo), "--node"])
    out = capsys.readouterr().out
    assert '+        "jade": "npm:pug@^3.0.2",' in out
