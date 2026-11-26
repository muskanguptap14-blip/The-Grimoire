"""Frozen data models shared by every Grimoire stage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SEVERITIES = ("CRITICAL", "ERROR", "WARNING", "INFO")
REPAIR_CLASSES = ("AUTOMATIC", "MANUAL")
CATEGORIES = (
    "SYNTAX",
    "IMPORT",
    "DEPENDENCY",
    "MANIFEST",
    "UNSUPPORTED",
    "SAFETY",
)
# Categories that count toward the Cause of Death ranking.
DEATH_CATEGORIES = ("DEPENDENCY", "IMPORT", "MANIFEST", "SYNTAX")

# rule_id -> (category, severity, repair_class). Single source of truth for
# severity classification and automatic versus manual repair classification.
RULE_META: dict[str, tuple[str, str, str]] = {
    # Syntax
    "PRINT_STMT": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "EXCEPT_AS": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "RAISE_STMT": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "BACKTICKS": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "NE_OPERATOR": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "EXEC_STMT": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "OCTAL_LITERAL": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "STRING_PREFIX": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "BUILTINS": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "DICT_METHODS": ("SYNTAX", "ERROR", "AUTOMATIC"),
    "UNPARSEABLE": ("SYNTAX", "CRITICAL", "MANUAL"),
    "PATCH_REJECTED": ("SYNTAX", "ERROR", "MANUAL"),
    "BAD_ENCODING": ("SYNTAX", "ERROR", "MANUAL"),
    "UNREADABLE": ("SYNTAX", "ERROR", "MANUAL"),
    # Imports
    "OUTDATED_IMPORT": ("IMPORT", "ERROR", "AUTOMATIC"),
    "BROKEN_IMPORT": ("IMPORT", "ERROR", "MANUAL"),
    "UNKNOWN_IMPORT": ("IMPORT", "WARNING", "MANUAL"),
    # Dependencies
    "MISSING_DEPENDENCY": ("DEPENDENCY", "ERROR", "AUTOMATIC"),
    "RENAMED_PACKAGE": ("DEPENDENCY", "WARNING", "AUTOMATIC"),
    "REMOVED_PACKAGE": ("DEPENDENCY", "ERROR", "AUTOMATIC"),
    "BAD_PIN": ("DEPENDENCY", "ERROR", "AUTOMATIC"),
    "DUPLICATE_REQUIREMENT": ("DEPENDENCY", "WARNING", "AUTOMATIC"),
    # Manifests
    "MALFORMED_REQUIREMENT": ("MANIFEST", "ERROR", "AUTOMATIC"),
    "INVALID_MANIFEST": ("MANIFEST", "ERROR", "MANUAL"),
    # Unsupported analysis (never a pass)
    "UNSUPPORTED_LANGUAGE": ("UNSUPPORTED", "INFO", "MANUAL"),
    "UNSUPPORTED_MANIFEST": ("UNSUPPORTED", "INFO", "MANUAL"),
    # Safety
    "INVALID_REPO": ("SAFETY", "CRITICAL", "MANUAL"),
    "SYMLINK_ESCAPE": ("SAFETY", "ERROR", "MANUAL"),
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    category: str
    file: str
    line: int
    reason: str
    severity: str = "ERROR"
    repair_class: str = "MANUAL"

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"invalid severity: {self.severity!r}")
        if self.repair_class not in REPAIR_CLASSES:
            raise ValueError(f"invalid repair class: {self.repair_class!r}")
        if self.category not in CATEGORIES:
            raise ValueError(f"invalid category: {self.category!r}")

    def sort_key(self) -> tuple[str, int, str, str]:
        return (self.file, self.line, self.rule_id, self.reason)


def make_finding(
    rule_id: str,
    file: str,
    line: int,
    reason: str,
    *,
    repair_class: str | None = None,
    severity: str | None = None,
) -> Finding:
    """Build a Finding whose category, severity and repair class come from RULE_META."""
    category, default_severity, default_class = RULE_META[rule_id]
    return Finding(
        rule_id=rule_id,
        category=category,
        file=file,
        line=line,
        reason=reason,
        severity=severity or default_severity,
        repair_class=repair_class or default_class,
    )


def sorted_findings(findings: Any) -> tuple[Finding, ...]:
    return tuple(sorted(set(findings), key=Finding.sort_key))


@dataclass(frozen=True)
class FilePatch:
    path: str
    before: str
    after: str
    rules_applied: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatchResult:
    """Outcome of repairing one file: a patch, or findings explaining why not."""

    patch: FilePatch | None
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True)
class ProofResult:
    status: str  # ALIVE | STILL_DEAD | TIMED_OUT | UNVERIFIED
    exit_code: int | None = None
    log_lines: tuple[str, ...] = ()
    duration_note: str = ""

    def __post_init__(self) -> None:
        if self.status not in ("ALIVE", "STILL_DEAD", "TIMED_OUT", "UNVERIFIED"):
            raise ValueError(f"invalid proof status: {self.status!r}")


@dataclass(frozen=True)
class Report:
    findings: tuple[Finding, ...]
    cause_of_death: tuple[tuple[str, int], ...] = ()
    patches: tuple[FilePatch, ...] = ()
    diff: str = ""
    dockerfile: str = ""
    proof: ProofResult | None = None
    # (language, status, file_count); status is ANALYZED or UNSUPPORTED.
    coverage: tuple[tuple[str, str, int], ...] = ()
    project_types: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
