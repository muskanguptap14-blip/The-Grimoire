"""package.json modernizer (stretch, Req 10). Dependency-free, offline, table driven.

Only the manifest is touched: JavaScript sources are never read or rewritten, and no
npm command or registry lookup is made. All knowledge comes from ``data/node_map.json``.

Repairs are targeted text edits at the exact value spans, so every other byte of the
file (indentation, line endings, key order, array layout, escapes) is preserved. The
edited text is re-parsed and compared with the expected data; if that check ever fails,
the manifest is re-serialized with the JSON encoder instead.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

from .models import Finding, make_finding

# Sections whose entries can be repaired. peerDependencies are only reported on.
REPAIR_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies")
REPORT_SECTIONS = REPAIR_SECTIONS + ("peerDependencies",)

Version = tuple[int, int, int]


@lru_cache(maxsize=1)
def load_node_map() -> dict:
    text = resources.files("grimoire").joinpath("data/node_map.json").read_text(encoding="utf-8")
    return json.loads(text)


# --------------------------------------------------------------------------- npm ranges

_VERSION = re.compile(
    r"^v?(?P<major>\d+)(?:\.(?P<minor>\d+|[xX*]))?(?:\.(?P<patch>\d+|[xX*]))?(?:[-+][0-9A-Za-z.+-]*)?$"
)
_CLAUSE = re.compile(r"^(?P<op>\^|~|<=|>=|<|>|=)?(?P<ver>\S+)$")
_UNBOUNDED = object()


class _Unparseable(Exception):
    """A range clause is not plain semver (tag, URL, file path, alias, hyphen range...)."""


def _parts(text: str) -> list[int]:
    """Numeric parts of a version, truncated at the first wildcard. Raises _Unparseable."""
    m = _VERSION.match(text)
    if not m:
        raise _Unparseable(text)
    out: list[int] = []
    for key in ("major", "minor", "patch"):
        value = m.group(key)
        if value is None or value in ("x", "X", "*"):
            break
        out.append(int(value))
    return out


def _clause_bound(clause: str) -> object:
    """Exclusive upper bound of one clause, or _UNBOUNDED. Raises _Unparseable."""
    if clause in ("*", "x", "X"):
        return _UNBOUNDED
    m = _CLAUSE.match(clause)
    if not m:
        raise _Unparseable(clause)
    op, ver = m.group("op") or "", m.group("ver")
    parts = _parts(ver)
    n = len(parts)  # at least 1: the version pattern requires a numeric major
    major = parts[0]
    minor = parts[1] if n > 1 else 0
    patch = parts[2] if n > 2 else 0
    if op in (">", ">="):
        return _UNBOUNDED
    if op == "<":
        return (major, minor, patch)
    if op == "<=":
        if n == 3:
            return (major, minor, patch + 1)
        return (major, minor + 1, 0) if n == 2 else (major + 1, 0, 0)
    if op == "^":
        if major > 0 or n == 1:
            return (major + 1, 0, 0)
        if n == 2:
            return (0, minor + 1, 0)
        return (0, minor + 1, 0) if minor > 0 else (0, 0, patch + 1)
    if op == "~":
        return (major + 1, 0, 0) if n == 1 else (major, minor + 1, 0)
    # bare version or "=": partial versions behave like x-ranges, full versions are exact
    if n == 1:
        return (major + 1, 0, 0)
    if n == 2:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def upper_bound(spec: str) -> Version | None:
    """Exclusive upper bound of an npm range, or None when unbounded or not plain semver.

    None always means "do not flag": unknown input is never treated as outdated.
    """
    text = re.sub(r"(<=|>=|<|>|=|\^|~)\s+", r"\1", spec.strip())
    if not text:
        return None
    try:
        best: Version | None = None
        union: list[Version] = []
        for alternative in text.split("||"):
            alternative = alternative.strip()
            if " - " in alternative:
                return None  # hyphen ranges are left alone
            bounds: list[Version] = []
            for clause in alternative.split() or ["*"]:
                bound = _clause_bound(clause)
                if bound is not _UNBOUNDED:
                    bounds.append(bound)  # type: ignore[arg-type]
            if not bounds:
                return None  # one unbounded alternative makes the whole range unbounded
            union.append(min(bounds))
        best = max(union)
        return best
    except _Unparseable:
        return None


def _version_tuple(text: str) -> Version:
    parts = _parts(text)
    return tuple((parts + [0, 0, 0])[:3])  # type: ignore[return-value]


def is_outdated(spec: str, below: str) -> bool:
    """True when no version allowed by ``spec`` is >= ``below``."""
    bound = upper_bound(spec)
    return bound is not None and bound <= _version_tuple(below)


def is_registry_range(spec: str) -> bool:
    """True for plain semver ranges (``^1.2.3``, ``*``, ``1.x``); False for tags, URLs, aliases."""
    text = re.sub(r"(<=|>=|<|>|=|\^|~)\s+", r"\1", spec.strip())
    if not text or text.startswith("npm:"):
        return False
    try:
        for alternative in text.split("||"):
            if " - " in alternative:
                return False
            for clause in alternative.split() or ["*"]:
                _clause_bound(clause)
    except _Unparseable:
        return False
    return True


# --------------------------------------------------------------------------- JSON spans

_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def _locate(text: str) -> dict[tuple[str, ...], tuple[int, int, int]]:
    """Map key paths (objects only, any depth) to (start, end, line) of string values.

    ``text`` must already be valid JSON. Values inside arrays are skipped.
    """
    spans: dict[tuple[str, ...], tuple[int, int, int]] = {}
    stack: list[list] = []  # ["obj", current_key, expecting_key] or ["arr"]
    pos, n = 0, len(text)
    while pos < n:
        ch = text[pos]
        if ch == '"':
            m = _STRING.match(text, pos)
            if m is None:  # cannot happen for valid JSON
                break
            end = m.end()
            top = stack[-1] if stack else None
            if top is not None and top[0] == "obj":
                if top[2]:
                    top[1] = json.loads(m.group(0))
                    top[2] = False
                elif all(level[0] == "obj" for level in stack):
                    path = tuple(level[1] for level in stack)
                    spans[path] = (pos, end, text.count("\n", 0, pos) + 1)
            pos = end
            continue
        if ch == "{":
            stack.append(["obj", None, True])
        elif ch == "[":
            stack.append(["arr"])
        elif ch in "}]":
            stack.pop()
        elif ch == "," and stack and stack[-1][0] == "obj":
            stack[-1][2] = True
        pos += 1
    return spans


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not valid JSON")


def parse_manifest(text: str) -> tuple[dict | None, str]:
    """Parse package.json text. Returns (data, "") or (None, error message)."""
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except RecursionError:
        return None, "nesting is too deep"
    except ValueError as exc:  # includes JSONDecodeError
        line = getattr(exc, "lineno", 0)
        msg = getattr(exc, "msg", str(exc))
        return None, f"invalid JSON: {msg}" + (f" (line {line})" if line else "")
    if not isinstance(data, dict):
        return None, "package.json must contain a JSON object"
    return data, ""


def _error_line(message: str) -> int:
    m = re.search(r"\(line (\d+)\)$", message)
    return int(m.group(1)) if m else 1


# --------------------------------------------------------------------------- the fixer


def fix_manifest(text: str, file: str = "package.json") -> tuple[str, tuple[Finding, ...]]:
    """Repair package.json text from the offline mapping table.

    Idempotent and order preserving. Returns the (possibly unchanged) text and findings
    sorted by position. Unfixable problems become MANUAL findings and change nothing.
    """
    data, error = parse_manifest(text)
    if data is None:
        return text, (make_finding("INVALID_MANIFEST", file, _error_line(error), error),)

    table = load_node_map()
    spans = _locate(text)
    findings: list[Finding] = []
    edits: dict[tuple[str, ...], str] = {}  # path -> new string value

    def line_of(path: tuple[str, ...]) -> int:
        return spans[path][2] if path in spans else 1

    for section in REPORT_SECTIONS:
        deps = data.get(section)
        if not isinstance(deps, dict):
            continue
        for name, spec in deps.items():
            if not isinstance(spec, str) or spec.startswith("npm:"):
                continue  # not a registry range; npm aliases are left alone (idempotence)
            path = (section, name)
            if section in REPAIR_SECTIONS and name in table["renames"] and is_registry_range(spec):
                entry = table["renames"][name]
                alias = f"npm:{entry['new']}@{entry['range']}"
                edits[path] = alias
                findings.append(
                    make_finding(
                        "NODE_RENAMED_PACKAGE",
                        file,
                        line_of(path),
                        f"{name} was renamed to {entry['new']}; aliased as {alias} so require('{name}') keeps working",
                    )
                )
                continue
            rule = table["bad_ranges"].get(name)
            if section in REPAIR_SECTIONS and rule and is_outdated(spec, rule["below"]):
                edits[path] = rule["replacement"]
                findings.append(
                    make_finding(
                        "NODE_BAD_RANGE",
                        file,
                        line_of(path),
                        f"{name}@{spec} cannot resolve to {rule['below']} or newer; replaced with {rule['replacement']}",
                    )
                )
                continue
            if name in table["deprecated"]:
                findings.append(
                    make_finding(
                        "NODE_DEPRECATED_PACKAGE",
                        file,
                        line_of(path),
                        f"{name} is {table['deprecated'][name]}; left unchanged, needs human review",
                    )
                )

    engines = data.get("engines")
    rule = table["engines_node"]
    if isinstance(engines, dict) and isinstance(engines.get("node"), str):
        spec = engines["node"]
        if is_outdated(spec, rule["below"]):
            edits[("engines", "node")] = rule["replacement"]
            findings.append(
                make_finding(
                    "NODE_ENGINE_OUTDATED",
                    file,
                    line_of(("engines", "node")),
                    f"engines.node {spec!r} excludes every Node.js release from {rule['below']} on; replaced with {rule['replacement']!r}",
                )
            )

    ordered = tuple(sorted(findings, key=Finding.sort_key))
    if not edits:
        return text, ordered
    return _apply_edits(text, data, spans, edits), ordered


def _apply_edits(
    text: str,
    data: dict,
    spans: dict[tuple[str, ...], tuple[int, int, int]],
    edits: dict[tuple[str, ...], str],
) -> str:
    expected = json.loads(json.dumps(data))
    for path, value in edits.items():
        node = expected
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    out = text
    if all(path in spans for path in edits):
        for path in sorted(edits, key=lambda p: spans[p][0], reverse=True):
            start, end, _line = spans[path]
            out = out[:start] + json.dumps(edits[path], ensure_ascii=False) + out[end:]
        try:
            if json.loads(out) == expected:
                return out
        except ValueError:
            pass
    return _reserialize(text, expected)


def _reserialize(original: str, data: dict) -> str:
    """Fallback: re-encode with the original indent and line ending."""
    m = re.search(r'^([ \t]+)"', original, re.MULTILINE)
    indent: str | int = m.group(1) if m else 2
    eol = "\r\n" if "\r\n" in original else "\n"
    body = json.dumps(data, indent=indent, ensure_ascii=False, allow_nan=False)
    return body.replace("\n", eol) + eol
