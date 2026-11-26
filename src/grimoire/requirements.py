"""requirements.txt parser and fixer. Dependency-free, offline, table driven."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from .models import Finding, make_finding

_CLAUSE = r"(?:===|==|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9][A-Za-z0-9.*+!_-]*"
_NAME = re.compile(r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(?P<extras>\[[^\]]*\])?\s*(?P<rest>.*)$")
_SPEC = re.compile(rf"^(?:{_CLAUSE}(?:\s*,\s*{_CLAUSE})*)?$")
_OP_VER = re.compile(r"^(===|==|~=|!=|<=|>=|<|>)\s*(.+)$")
_VERSION = re.compile(r"^\d+(?:\.\d+)*")


@lru_cache(maxsize=1)
def load_packages_map() -> dict:
    text = resources.files("grimoire").joinpath("data/packages_map.json").read_text(encoding="utf-8")
    return json.loads(text)


def normalize(name: str) -> str:
    """PEP 503 normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Line:
    raw: str  # includes the line ending
    kind: str  # BLANK | COMMENT | OPTION | REQUIREMENT | MALFORMED
    name: str = ""
    extras: str = ""
    spec: str = ""  # specifier text, e.g. ">=1.0,<2"
    spec_span: tuple[int, int] = (0, 0)  # span of spec within raw
    name_span: tuple[int, int] = (0, 0)
    lineno: int = 0


def _split_comment(body: str) -> str:
    """Body of a line without a trailing ``# comment``."""
    m = re.search(r"\s#", body)
    return body[: m.start()] if m else body


def parse_line(raw: str, lineno: int) -> Line:
    stripped = raw.strip()
    if not stripped:
        return Line(raw, "BLANK", lineno=lineno)
    if stripped.startswith("#"):
        return Line(raw, "COMMENT", lineno=lineno)
    if stripped.startswith("-") or "://" in stripped.split(";")[0].split("@")[0]:
        return Line(raw, "OPTION", lineno=lineno)
    body = _split_comment(raw.rstrip("\r\n"))
    lead = len(body) - len(body.lstrip())
    body_nm = body[lead:]
    marker_at = body_nm.find(";")
    core = body_nm if marker_at < 0 else body_nm[:marker_at]
    m = _NAME.match(core.rstrip())
    if not m:
        return Line(raw, "MALFORMED", lineno=lineno)
    rest = m.group("rest").strip()
    if rest.startswith("@"):
        if len(rest) > 1 and rest[1:].strip():
            return Line(raw, "OPTION", lineno=lineno)  # direct URL reference, kept verbatim
        return Line(raw, "MALFORMED", lineno=lineno)
    if not _SPEC.match(rest):
        return Line(raw, "MALFORMED", lineno=lineno)
    name_span = (lead + m.start("name"), lead + m.end("name"))
    if rest:
        start = lead + m.start("rest") + (len(m.group("rest")) - len(m.group("rest").lstrip()))
        spec_span = (start, start + len(rest))
    else:
        spec_span = (name_span[1], name_span[1])
    return Line(
        raw=raw,
        kind="REQUIREMENT",
        name=m.group("name"),
        extras=m.group("extras") or "",
        spec=rest,
        spec_span=spec_span,
        name_span=name_span,
        lineno=lineno,
    )


def parse(text: str) -> list[Line]:
    return [parse_line(raw, i) for i, raw in enumerate(text.splitlines(keepends=True), start=1)]


def render(lines: list[Line]) -> str:
    return "".join(line.raw for line in lines)


def requirement_name(spec: str) -> str | None:
    """Distribution name of a PEP 508 style string such as ``requests>=2``, or None."""
    m = _NAME.match(spec.strip())
    return m.group("name") if m else None


def declared_names(text: str) -> set[str]:
    return {normalize(ln.name) for ln in parse(text) if ln.kind == "REQUIREMENT"}


# --------------------------------------------------------------------------- versions


def _version_tuple(text: str) -> tuple[int, ...] | None:
    m = _VERSION.match(text.strip())
    return tuple(int(p) for p in m.group(0).split(".")) if m else None


def _pad(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


def is_bad_pin(spec: str, below: str) -> bool:
    """True when an upper-bounding clause (==, ===, <=, <, ~=) names a version below ``below``."""
    limit = _version_tuple(below)
    if limit is None:
        return False
    for clause in spec.split(","):
        m = _OP_VER.match(clause.strip())
        if not m or m.group(1) not in ("==", "===", "<=", "<", "~="):
            continue
        version = _version_tuple(m.group(2))
        if version is None:
            continue
        a, b = _pad(version, limit)
        if a < b:
            return True
    return False


# --------------------------------------------------------------------------- fixer


def fix_requirements(text: str, file: str = "requirements.txt") -> tuple[str, tuple[Finding, ...]]:
    """Repair requirements text from the offline mapping tables.

    Idempotent. Comments, options and ``-r`` lines are kept verbatim; kept lines
    keep their relative order; duplicates keep the first occurrence.
    """
    table = load_packages_map()
    renames = {normalize(k): v for k, v in table["renames"].items()}
    removed = {normalize(n) for n in table["removed"]}
    bad_pins = {normalize(k): v for k, v in table["bad_pins"].items()}
    findings: list[Finding] = []
    out: list[str] = []
    seen: set[str] = set()
    for line in parse(text):
        if line.kind == "MALFORMED":
            body = line.raw.rstrip("\r\n")
            eol = line.raw[len(body):] or "\n"
            findings.append(
                make_finding(
                    "MALFORMED_REQUIREMENT",
                    file,
                    line.lineno,
                    f"cannot parse requirement {body.strip()!r}; commented out, needs human review",
                )
            )
            out.append(f"# grimoire: malformed requirement commented out: {body.strip()}{eol}")
            continue
        if line.kind != "REQUIREMENT":
            out.append(line.raw)
            continue
        key = normalize(line.name)
        if key in removed:
            findings.append(
                make_finding(
                    "REMOVED_PACKAGE",
                    file,
                    line.lineno,
                    f"{line.name} is obsolete on Python 3.11 (stdlib or dead backport); line dropped",
                )
            )
            continue
        raw = line.raw
        name_text = line.name
        spec = line.spec
        # spec is edited before the name so the name span stays valid
        entry = bad_pins.get(normalize(renames.get(key, line.name)))
        if entry and spec and is_bad_pin(spec, entry["below"]):
            findings.append(
                make_finding(
                    "BAD_PIN",
                    file,
                    line.lineno,
                    f"{line.name}{spec} has no Python 3.11 build; replaced with {entry['replacement']}",
                )
            )
            s, e = line.spec_span
            raw = raw[:s] + entry["replacement"] + raw[e:]
        if key in renames:
            name_text = renames[key]
            findings.append(
                make_finding(
                    "RENAMED_PACKAGE",
                    file,
                    line.lineno,
                    f"{line.name} was renamed on PyPI; now {name_text}",
                )
            )
            s, e = line.name_span
            raw = raw[:s] + name_text + raw[e:]
        final_key = normalize(name_text)
        if final_key in seen:
            findings.append(
                make_finding(
                    "DUPLICATE_REQUIREMENT",
                    file,
                    line.lineno,
                    f"{name_text} is already declared; duplicate dropped",
                )
            )
            continue
        seen.add(final_key)
        out.append(raw)
    return "".join(out), tuple(sorted(findings, key=Finding.sort_key))


def add_requirements(text: str, names: list[str]) -> str:
    """Append bare requirement names that are not already declared (sorted, idempotent)."""
    declared = declared_names(text)
    additions = sorted({n for n in names if normalize(n) not in declared}, key=normalize)
    if not additions:
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "".join(f"{n}\n" for n in additions)
