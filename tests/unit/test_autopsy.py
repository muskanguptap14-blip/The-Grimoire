import random

import pytest

from grimoire import autopsy, scan
from grimoire.models import Finding


def make_repo(root, files):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
    return root


def rules(report):
    return sorted((f.file, f.line, f.rule_id) for f in report.findings)


def test_syntax_errors_py2_and_unparseable(tmp_path):
    make_repo(tmp_path, {
        "old.py": 'print "x"\ntry:\n    pass\nexcept ValueError, e:\n    pass\n',
        "broken.py": "def f(:\n    pass\n",
        "fine.py": "x = 1\n",
    })
    report = autopsy.autopsy(tmp_path)
    got = rules(report)
    assert ("old.py", 1, "PRINT_STMT") in got
    assert ("old.py", 4, "EXCEPT_AS") in got
    assert ("broken.py", 1, "UNPARSEABLE") in got
    assert not [f for f in report.findings if f.file == "fine.py"]
    by_rule = {f.rule_id: f for f in report.findings}
    assert by_rule["PRINT_STMT"].repair_class == "AUTOMATIC" and by_rule["PRINT_STMT"].severity == "ERROR"
    assert by_rule["UNPARSEABLE"].repair_class == "MANUAL" and by_rule["UNPARSEABLE"].severity == "CRITICAL"


def test_import_analysis(tmp_path):
    make_repo(tmp_path, {
        "app.py": ("import os\nimport json\nimport urllib2\nimport local\nimport pkg.gone\nimport mystery\n"
                   "import yaml\nimport requests\nfrom . import sibling\nfrom .nothere import z\n"
                   "try:\n    import optional_thing\nexcept ImportError:\n    optional_thing = None\n"),
        "local.py": "x = 1\n",
        "sibling.py": "y = 1\n",
        "pkg/__init__.py": "",
        "requirements.txt": "PyYAML\n",
    })
    report = autopsy.autopsy(tmp_path)
    got = {(f.rule_id, f.line) for f in report.findings if f.file == "app.py"}
    assert ("OUTDATED_IMPORT", 3) in got
    assert ("BROKEN_IMPORT", 5) in got
    assert ("UNKNOWN_IMPORT", 6) in got
    assert ("MISSING_DEPENDENCY", 8) in got
    assert ("BROKEN_IMPORT", 10) in got
    assert not {l for r, l in got if l in (1, 2, 4, 7, 9, 12)}
    missing = [f for f in report.findings if f.rule_id == "MISSING_DEPENDENCY"][0]
    assert missing.repair_class == "AUTOMATIC"


def test_missing_dependency_is_manual_without_requirements_txt(tmp_path):
    make_repo(tmp_path, {"a.py": "import requests\n"})
    f = [x for x in autopsy.autopsy(tmp_path).findings if x.rule_id == "MISSING_DEPENDENCY"]
    assert len(f) == 1 and f[0].repair_class == "MANUAL"


def test_declared_via_pyproject_setup_cfg_setup_py(tmp_path):
    make_repo(tmp_path, {
        "a.py": "import requests\nimport yaml\nimport numpy\nimport six\n",
        "pyproject.toml": '[project]\nname = "x"\ndependencies = ["requests>=2"]\n',
        "setup.cfg": "[options]\ninstall_requires =\n    PyYAML\n",
        "setup.py": "from setuptools import setup\nsetup(name='x', install_requires=['numpy'])\n",
    })
    report = autopsy.autopsy(tmp_path)
    got = [(f.rule_id, f.line) for f in report.findings if f.file == "a.py"]
    assert got == [("MISSING_DEPENDENCY", 4)]


def test_invalid_manifests_reported(tmp_path):
    make_repo(tmp_path, {"pyproject.toml": "[project\n", "setup.cfg": "no header\n"})
    report = autopsy.autopsy(tmp_path)
    assert sorted(f.file for f in report.findings if f.rule_id == "INVALID_MANIFEST") == ["pyproject.toml", "setup.cfg"]


def test_dependency_findings_from_requirements(tmp_path):
    make_repo(tmp_path, {"requirements.txt": "PIL==1.1.7\ndistribute\n!!x\nnumpy\nnumpy\n"})
    report = autopsy.autopsy(tmp_path)
    ids = sorted(f.rule_id for f in report.findings)
    assert ids == ["BAD_PIN", "DUPLICATE_REQUIREMENT", "MALFORMED_REQUIREMENT", "REMOVED_PACKAGE", "RENAMED_PACKAGE"]
    assert all(f.repair_class == "AUTOMATIC" for f in report.findings)


def test_unsupported_is_never_a_pass(tmp_path):
    make_repo(tmp_path, {"index.js": "var a;", "app.go": "package main", "package.json": "{}"})
    report = autopsy.autopsy(tmp_path)
    assert {f.rule_id for f in report.findings} == {"UNSUPPORTED_LANGUAGE", "UNSUPPORTED_MANIFEST"}
    assert report.cause_of_death == ()
    assert ("javascript", "UNSUPPORTED", 1) in report.coverage
    assert ("package.json", "UNSUPPORTED", 1) in report.coverage
    assert not any(status == "ANALYZED" for _, status, _ in report.coverage)
    assert "no failures detected by supported analyzers" in autopsy.format_report(report)


def test_error_handling_for_bad_files(tmp_path):
    make_repo(tmp_path, {"bin.py": b"\x00\x01\x02", "latin.py": b"s = '\xe9'\n", "ok.py": "x = 1\n"})
    report = autopsy.autopsy(tmp_path)
    assert sorted((f.file, f.rule_id) for f in report.findings) == [("bin.py", "BAD_ENCODING"), ("latin.py", "BAD_ENCODING")]


def test_invalid_repo_path(tmp_path):
    report = autopsy.autopsy(tmp_path / "nope")
    assert [f.rule_id for f in report.findings] == ["INVALID_REPO"]


def test_cause_of_death_ranking_ties_alphabetical():
    def f(cat):
        return Finding("R", cat, "a", 1, "r", "ERROR", "MANUAL")

    ranked = autopsy.cause_of_death([f("SYNTAX"), f("IMPORT"), f("DEPENDENCY"), f("DEPENDENCY"), f("SYNTAX"), f("MANIFEST")])
    assert ranked == (("DEPENDENCY", 2), ("SYNTAX", 2), ("IMPORT", 1), ("MANIFEST", 1))
    info = Finding("R", "SYNTAX", "a", 1, "r", "INFO", "MANUAL")
    assert autopsy.cause_of_death([info]) == ()


def test_report_deterministic_and_independent_of_scan_order(tmp_path, monkeypatch):
    make_repo(tmp_path, {
        "a.py": 'print "a"\nimport urllib2\n', "b.py": "import zzz\n", "c/d.py": "def f(:\n",
        "requirements.txt": "PIL\n",
    })
    base = autopsy.autopsy(tmp_path)
    assert autopsy.autopsy(tmp_path) == base
    real = scan.scan_repo

    def shuffled(root):
        result = real(root)
        files = list(result.files)
        random.Random(7).shuffle(files)
        return type(result)(tuple(files), result.languages, result.project_types, result.findings)

    monkeypatch.setattr(scan, "scan_repo", shuffled)
    assert autopsy.autopsy(tmp_path) == base


def test_source_is_not_modified(tmp_path):
    make_repo(tmp_path, {"a.py": 'print "a"\n', "requirements.txt": "PIL\n"})
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    autopsy.autopsy(tmp_path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_json_output_has_no_absolute_paths(tmp_path):
    make_repo(tmp_path, {"a.py": 'print "a"\n'})
    assert str(tmp_path) not in autopsy.report_json(autopsy.autopsy(tmp_path))
