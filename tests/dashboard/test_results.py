"""Pure payload logic: outcome classification and the rule-to-action table."""

import pytest

from grimoire.dashboard import results
from grimoire.models import RULE_META, FilePatch, ProofResult, Report, make_finding


def _f(rule="BAD_PIN", **kw):
    return make_finding(rule, "a.py", 1, "x", **kw)


def test_action_table_covers_every_rule():
    assert set(results.RULE_ACTIONS) == set(RULE_META)
    assert all(results.RULE_ACTIONS.values())


def test_plan_groups_by_rule():
    plan = results.build_plan([_f("BAD_PIN"), _f("BAD_PIN"), make_finding("PRINT_STMT", "b.py", 2, "x")])
    assert [p["rule_id"] for p in plan] == ["BAD_PIN", "PRINT_STMT"]
    assert plan[0]["count"] == 2 and plan[0]["files"] == ["a.py"]
    assert plan[1]["action"] == results.RULE_ACTIONS["PRINT_STMT"]


@pytest.mark.parametrize(
    "report,outcome",
    [
        (Report((), proof=ProofResult("ALIVE", 0)), "SUCCESS"),
        (Report((make_finding("UNSUPPORTED_LANGUAGE", "a.go", 0, "x"),), proof=ProofResult("ALIVE", 0)), "SUCCESS"),
        (Report((_f(),), proof=ProofResult("ALIVE", 0)), "PARTIAL"),
        (Report((), patches=(FilePatch("a", "x", "y"),), proof=ProofResult("UNVERIFIED")), "PARTIAL"),
        (Report((), patches=(FilePatch("a", "x", "y"),)), "PARTIAL"),
        (Report((_f(),), proof=ProofResult("STILL_DEAD", 1)), "FAILURE"),
        (Report((), proof=ProofResult("TIMED_OUT")), "FAILURE"),
        (Report((make_finding("INVALID_REPO", ".", 0, "x"),)), "FAILURE"),
    ],
)
def test_classify_outcome(report, outcome):
    got, reason = results.classify_outcome(report)
    assert got == outcome and reason


def test_stats_from_report_only():
    report = Report(
        (_f("MISSING_DEPENDENCY"), _f("BROKEN_IMPORT")),
        before_findings=(_f("BAD_PIN"), _f("PRINT_STMT"), _f("BROKEN_IMPORT"), _f("MISSING_DEPENDENCY")),
        patches=(FilePatch("a", "x", "y"),),
        coverage=(("python", "ANALYZED", 3),),
    )
    s = results.stats(report)
    assert s == {
        "issues_before": 4,
        "issues_after": 2,
        "automatic_fixed": 2,
        "manual_remaining": 1,
        "files_scanned": 3,
        "files_patched": 1,
    }
