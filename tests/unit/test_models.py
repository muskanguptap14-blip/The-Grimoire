import dataclasses

import pytest

from grimoire.models import FilePatch, Finding, ProofResult, Report, RULE_META, make_finding


def test_finding_is_frozen_hashable_and_replaceable():
    f = Finding("R", "SYNTAX", "a.py", 1, "why", "ERROR", "AUTOMATIC")
    assert hash(f) == hash(dataclasses.replace(f))
    assert dataclasses.replace(f, line=2).line == 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.line = 3  # type: ignore[misc]


def test_invalid_values_rejected():
    with pytest.raises(ValueError):
        Finding("R", "SYNTAX", "a.py", 1, "why", "LOUD", "MANUAL")
    with pytest.raises(ValueError):
        Finding("R", "SYNTAX", "a.py", 1, "why", "ERROR", "MAYBE")
    with pytest.raises(ValueError):
        ProofResult("MAYBE")


def test_rule_meta_is_valid_and_make_finding_uses_it():
    for rule_id in RULE_META:
        make_finding(rule_id, "f", 1, "r")
    f = make_finding("UNPARSEABLE", "a.py", 3, "bad")
    assert (f.severity, f.repair_class, f.category) == ("CRITICAL", "MANUAL", "SYNTAX")


def test_report_and_patch_construct():
    patch = FilePatch("a.py", "a", "b", ("PRINT_STMT",))
    report = Report((), patches=(patch,))
    assert report.to_dict()["patches"][0]["path"] == "a.py"
