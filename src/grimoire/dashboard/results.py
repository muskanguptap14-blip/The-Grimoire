"""Pure payload builders: turn engine Reports into JSON-ready dashboards data.

Nothing here runs code or touches the filesystem. Every number is computed from the
Report it is given.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..models import RULE_META, SEVERITIES, Finding, Report

# rule_id -> what Grimoire does about it. Must cover every RULE_META key (tested).
RULE_ACTIONS: dict[str, str] = {
    "PRINT_STMT": "Rewrite print statements as print() calls",
    "EXCEPT_AS": "Rewrite 'except E, e' as 'except E as e'",
    "RAISE_STMT": "Rewrite Python 2 raise forms as raise E(...)",
    "BACKTICKS": "Replace backtick repr with repr()",
    "NE_OPERATOR": "Replace <> with !=",
    "EXEC_STMT": "Rewrite exec statements as exec() calls",
    "OCTAL_LITERAL": "Rewrite legacy octal literals with the 0o prefix",
    "STRING_PREFIX": "Rewrite Python 2 string and integer literal prefixes",
    "BUILTINS": "Replace removed builtins (xrange, raw_input, unicode, long, basestring)",
    "DICT_METHODS": "Rewrite dict.has_key and iter* methods",
    "UNPARSEABLE": "Manual: the file parses under neither Python 3 nor Python 2; fix the syntax by hand",
    "PATCH_REJECTED": "Manual: the automatic patch did not produce valid Python 3, so the original was kept",
    "BAD_ENCODING": "Manual: re-save the file as UTF-8 or declare its encoding",
    "UNREADABLE": "Manual: the file could not be read; check its permissions",
    "OUTDATED_IMPORT": "Rewrite the import to its Python 3 module",
    "BROKEN_IMPORT": "Manual: the imported module cannot be found in the repository; restore or fix it",
    "UNKNOWN_IMPORT": "Manual: confirm the module is a real dependency and declare it",
    "MISSING_DEPENDENCY": "Add the missing distribution to requirements.txt",
    "RENAMED_PACKAGE": "Replace the package with its current name in requirements",
    "REMOVED_PACKAGE": "Remove the package that no longer exists on the index",
    "BAD_PIN": "Replace an unsatisfiable pin with a working specifier",
    "DUPLICATE_REQUIREMENT": "Drop the duplicate requirement line",
    "NODE_RENAMED_PACKAGE": "Alias the renamed npm package to its replacement so existing require() calls keep working",
    "NODE_BAD_RANGE": "Replace an npm range that cannot reach a working release with a current range",
    "NODE_DEPRECATED_PACKAGE": "Manual: the npm package is deprecated upstream and has no safe automatic replacement",
    "NODE_ENGINE_OUTDATED": "Replace an engines.node range that excludes every supported Node.js release",
    "MALFORMED_REQUIREMENT": "Repair the malformed requirement line",
    "INVALID_MANIFEST": "Manual: the manifest cannot be parsed; fix it by hand",
    "UNSUPPORTED_LANGUAGE": "None: Grimoire has no analyzer for this language, so nothing was checked",
    "UNSUPPORTED_MANIFEST": "None: Grimoire has no analyzer for this manifest, so nothing was checked",
    "INVALID_REPO": "Manual: choose a readable directory",
    "SYMLINK_ESCAPE": "Manual: a symlink points outside the repository and was skipped",
}


def finding_dict(f: Finding) -> dict[str, Any]:
    return asdict(f)


def severity_counts(findings: Any) -> dict[str, int]:
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        counts[f.severity] += 1
    return counts


def _count_by(findings: Any, attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        key = getattr(f, attr)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_plan(findings: Any) -> list[dict[str, Any]]:
    """Group findings by rule into a repair plan (sorted by rule id)."""
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.rule_id, []).append(f)
    plan = []
    for rule_id in sorted(groups):
        items = groups[rule_id]
        category, severity, repair_class = RULE_META[rule_id]
        plan.append(
            {
                "rule_id": rule_id,
                "category": category,
                "severity": items[0].severity,
                "repair_class": items[0].repair_class,
                "count": len(items),
                "files": sorted({f.file for f in items}),
                "action": RULE_ACTIONS[rule_id],
            }
        )
    return plan


def _cause(report: Report) -> list[dict[str, Any]]:
    return [{"category": c, "count": n} for c, n in report.cause_of_death]


def _coverage(report: Report) -> list[dict[str, Any]]:
    return [{"language": lang, "status": status, "files": n} for lang, status, n in report.coverage]


def autopsy_payload(report: Report) -> dict[str, Any]:
    findings = report.findings
    return {
        "summary": {
            "files_by_language": {lang: n for lang, _s, n in report.coverage},
            "project_types": list(report.project_types),
            "coverage": _coverage(report),
            "counts": {
                "total": len(findings),
                "severity": severity_counts(findings),
                "category": _count_by(findings, "category"),
                "repair_class": _count_by(findings, "repair_class"),
            },
        },
        "findings": [finding_dict(f) for f in findings],
        "cause_of_death": _cause(report),
        "plan": build_plan(findings),
    }


def _blocking(findings: Any) -> list[Finding]:
    return [f for f in findings if f.severity != "INFO"]


def classify_outcome(report: Report) -> tuple[str, str]:
    """Return (SUCCESS | PARTIAL | FAILURE, reason). Pure function of the Report."""
    if any(f.rule_id == "INVALID_REPO" for f in report.findings):
        return "FAILURE", "the repository path is not a readable directory"
    status = report.proof.status if report.proof else None
    if status in ("STILL_DEAD", "TIMED_OUT"):
        detail = "did not finish before the timeout" if status == "TIMED_OUT" else "failed or could not be run"
        return "FAILURE", f"proof {status}: the repaired project {detail}"
    remaining = _blocking(report.findings)
    if status == "ALIVE" and not remaining:
        return "SUCCESS", "the repaired project ran offline and exited 0 with no findings remaining"
    if remaining:
        return "PARTIAL", f"{len(remaining)} finding(s) remain after automatic repair"
    if status == "UNVERIFIED":
        return "PARTIAL", "repairs applied but the project could not be verified: " + (
            report.proof.log_lines[0] if report.proof and report.proof.log_lines else "no detail"
        )
    return "PARTIAL", "repairs applied but no proof was requested"


def stats(report: Report) -> dict[str, int]:
    before = _blocking(report.before_findings)
    after = _blocking(report.findings)
    auto_before = sum(1 for f in before if f.repair_class == "AUTOMATIC")
    auto_after = sum(1 for f in after if f.repair_class == "AUTOMATIC")
    return {
        "issues_before": len(before),
        "issues_after": len(after),
        "automatic_fixed": max(0, auto_before - auto_after),
        "manual_remaining": sum(1 for f in after if f.repair_class == "MANUAL"),
        "files_scanned": sum(n for _l, _s, n in report.coverage),
        "files_patched": len(report.patches),
    }


def result_payload(report: Report) -> dict[str, Any]:
    outcome, reason = classify_outcome(report)
    return {
        "outcome": outcome,
        "reason": reason,
        "stats": stats(report),
        "before": {
            "findings": [finding_dict(f) for f in report.before_findings],
            "counts": severity_counts(report.before_findings),
        },
        "after": {
            "findings": [finding_dict(f) for f in report.findings],
            "counts": severity_counts(report.findings),
        },
        "patches": [
            {"path": p.path, "rules": list(p.rules_applied), "before": p.before, "after": p.after}
            for p in report.patches
        ],
        "diff": report.diff,
        "dockerfile": report.dockerfile,
        "validation": [{"name": n, "status": s, "detail": d} for n, s, d in report.validation],
        "proof": (
            {
                "status": report.proof.status,
                "exit_code": report.proof.exit_code,
                "log_lines": list(report.proof.log_lines),
            }
            if report.proof
            else None
        ),
        "cause_of_death": _cause(report),
        "coverage": _coverage(report),
        "project_types": list(report.project_types),
    }


def failure_payload(reason: str) -> dict[str, Any]:
    return {"outcome": "FAILURE", "reason": reason}
