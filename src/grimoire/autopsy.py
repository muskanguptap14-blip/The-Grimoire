"""Autopsy: scan a repository and build the structured diagnostic Report (no patching)."""

from __future__ import annotations

import ast
import configparser
import difflib
import json
import os
import sys
import tomllib
from pathlib import PurePosixPath

from . import codemods, imports, py2parse, requirements, scan
from .models import (
    DEATH_CATEGORIES,
    Finding,
    Report,
    make_finding,
    sorted_findings,
)

STDLIB = sys.stdlib_module_names


# --------------------------------------------------------------------------- helpers


def cause_of_death(findings: tuple[Finding, ...] | list[Finding]) -> tuple[tuple[str, int], ...]:
    """Categories ranked by finding count, ties broken alphabetically. INFO findings are excluded."""
    counts: dict[str, int] = {}
    for f in findings:
        if f.category in DEATH_CATEGORIES and f.severity != "INFO":
            counts[f.category] = counts.get(f.category, 0) + 1
    return tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _changed_lines(before: str, after: str) -> list[int]:
    a, b = before.splitlines(), after.splitlines()
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return [i1 + 1 for tag, i1, _i2, _j1, _j2 in matcher.get_opcodes() if tag != "equal"]


def _python2_findings(source: str, path: str) -> list[Finding]:
    """One finding per changed hunk per codemod rule (each rule run alone on the original)."""
    findings: list[Finding] = []
    for rule in codemods.RULES:
        try:
            after, applied = codemods.apply_syntax_rules(source, (rule,))
        except py2parse.Py2ParseError:
            continue
        if not applied:
            continue
        for line in _changed_lines(source, after):
            findings.append(
                make_finding(rule.RULE_ID, path, line, f"Python 2 construct handled by rule {rule.RULE_ID}")
            )
    return findings


# --------------------------------------------------------------------------- declared deps


def _setup_py_requires(source: str) -> set[str]:
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in ("install_requires", "setup_requires", "tests_require"):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        name = requirements.requirement_name(elt.value)
                        if name:
                            names.add(requirements.normalize(name))
    return names


def _manifest_deps(path: str, text: str) -> tuple[set[str], list[Finding]]:
    """Declared dependency names and findings for pyproject.toml / setup.cfg."""
    names: set[str] = set()
    findings: list[Finding] = []
    if path.endswith("pyproject.toml"):
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            return names, [make_finding("INVALID_MANIFEST", path, 0, f"invalid TOML: {exc}")]
        for spec in data.get("project", {}).get("dependencies", []) or []:
            name = requirements.requirement_name(str(spec))
            if name:
                names.add(requirements.normalize(name))
        poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}
        for key in poetry:
            if key.lower() != "python":
                names.add(requirements.normalize(key))
    else:
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(text)
        except configparser.Error as exc:
            return names, [make_finding("INVALID_MANIFEST", path, 0, f"invalid setup.cfg: {exc}")]
        raw = parser.get("options", "install_requires", fallback="")
        for line in raw.splitlines():
            name = requirements.requirement_name(line) if line.strip() else None
            if name:
                names.add(requirements.normalize(name))
    return names, findings


# --------------------------------------------------------------------------- import resolution


class _LocalIndex:
    """Answers whether a dotted module exists inside the repository."""

    def __init__(self, root: str) -> None:
        self.root = root

    def _exists(self, base: str, parts: list[str]) -> bool:
        rel = os.path.join(base, *parts)
        return os.path.isfile(rel + ".py") or os.path.isdir(rel)

    def bases(self, file: str) -> list[str]:
        file_dir = os.path.join(self.root, *PurePosixPath(file).parent.parts)
        return [self.root, os.path.join(self.root, "src"), file_dir]

    def top_level(self, top: str, file: str) -> bool:
        return any(self._exists(b, [top]) for b in self.bases(file))

    def resolves(self, dotted: str, file: str) -> bool:
        parts = dotted.split(".")
        return any(self._exists(b, parts) for b in self.bases(file))

    def relative(self, file: str, level: int, module: str) -> bool:
        base = os.path.join(self.root, *PurePosixPath(file).parent.parts)
        for _ in range(level - 1):
            base = os.path.dirname(base)
        if not module:
            return os.path.isdir(base)
        return self._exists(base, module.split("."))


def _import_findings(
    refs: list[imports.ImportRef],
    path: str,
    index: _LocalIndex,
    declared: set[str],
    have_requirements_txt: bool,
) -> tuple[list[Finding], list[tuple[str, str]]]:
    """Findings for one file's imports, plus (dist, first_file) for missing dependencies."""
    table = requirements.load_packages_map()
    import_names = table["import_names"]
    renames = {requirements.normalize(k): requirements.normalize(v) for k, v in table["renames"].items()}
    declared_canon = {renames.get(d, d) for d in declared}
    findings: list[Finding] = []
    missing: list[tuple[str, str]] = []
    for ref in refs:
        if ref.level:
            if not index.relative(path, ref.level, ref.module):
                shown = "." * ref.level + ref.module
                findings.append(
                    make_finding("BROKEN_IMPORT", path, ref.line, f"relative import {shown!r} does not resolve inside the repository")
                )
            continue
        top = ref.module.split(".")[0]
        entry = imports.lookup(ref.module) or imports.lookup(top)
        if entry is not None:
            findings.append(
                make_finding(
                    "OUTDATED_IMPORT",
                    path,
                    ref.line,
                    f"{top} was removed or renamed in Python 3; use {entry['new']}",
                )
            )
        elif top in STDLIB:
            continue
        elif index.top_level(top, path):
            if not index.resolves(ref.module, path):
                findings.append(
                    make_finding("BROKEN_IMPORT", path, ref.line, f"module {ref.module!r} not found in local package {top!r}")
                )
        else:
            dist = requirements.normalize(import_names.get(top, top))
            if dist in declared_canon or requirements.normalize(top) in declared_canon:
                continue
            if ref.guarded:
                continue  # optional import behind try/except ImportError
            if top in import_names:
                findings.append(
                    make_finding(
                        "MISSING_DEPENDENCY",
                        path,
                        ref.line,
                        f"{top!r} is imported but {import_names[top]} is not declared in any manifest",
                        repair_class="AUTOMATIC" if have_requirements_txt else "MANUAL",
                    )
                )
                missing.append((import_names[top], path))
            else:
                findings.append(
                    make_finding(
                        "UNKNOWN_IMPORT",
                        path,
                        ref.line,
                        f"{top!r} is not stdlib, not in the repository and not declared; no offline mapping exists",
                    )
                )
    return findings, missing


# --------------------------------------------------------------------------- main entry


def autopsy(root: str | os.PathLike[str]) -> Report:
    """Diagnose a repository. Pure analysis: nothing is written."""
    root_str = os.fspath(root)
    scanned = scan.scan_repo(root_str)
    findings: list[Finding] = list(scanned.findings)
    if scanned.files == () and any(f.rule_id == "INVALID_REPO" for f in findings):
        return Report(sorted_findings(findings), (), project_types=(), coverage=())

    index = _LocalIndex(os.path.realpath(root_str))
    declared: set[str] = set()
    have_req_txt = any(PurePosixPath(p).parent.as_posix() == "." for p in scanned.paths("requirements"))

    # manifests first: declared dependencies feed import resolution
    for path in scanned.paths("requirements"):
        src, err = scan.read_source(root_str, path)
        if err:
            findings.append(err)
            continue
        _fixed, req_findings = requirements.fix_requirements(src.text, path)
        findings.extend(req_findings)
        declared |= requirements.declared_names(src.text)
    for path in scanned.paths("python-manifest"):
        src, err = scan.read_source(root_str, path)
        if err:
            findings.append(err)
            continue
        names, manifest_findings = _manifest_deps(path, src.text)
        declared |= names
        findings.extend(manifest_findings)
    for path in scanned.paths("node-manifest"):
        findings.append(
            make_finding("UNSUPPORTED_MANIFEST", path, 0, "package.json detected; Node.js analysis is not supported, nothing was checked")
        )

    sources: dict[str, scan.SourceFile] = {}
    for path in scanned.paths("python"):
        src, err = scan.read_source(root_str, path)
        if err:
            findings.append(err)
            continue
        sources[path] = src
        if PurePosixPath(path).name == "setup.py":
            declared |= _setup_py_requires(src.text)

    for path in sorted(sources):
        text = sources[path].text
        kind = py2parse.classify(text)
        analysis_source: str | None = None
        if kind == py2parse.PY3:
            analysis_source = text
        elif kind == py2parse.PY2:
            findings.extend(_python2_findings(text, path))
            result = codemods.apply_all(text, path, imports=False)
            if result.patch is not None:
                analysis_source = result.patch.after
            else:
                findings.extend(result.findings)
        else:
            line, msg = py2parse.python3_syntax_error(text) or (0, "invalid syntax")
            findings.append(
                make_finding("UNPARSEABLE", path, line, f"parses under neither Python 3 nor Python 2 grammar: {msg}")
            )
        if analysis_source is None:
            continue
        tree = ast.parse(analysis_source)
        file_findings, _missing = _import_findings(
            imports.collect_imports(tree), path, index, declared, have_req_txt
        )
        findings.extend(file_findings)

    findings.extend(_unsupported_findings(scanned))
    # one MISSING_DEPENDENCY per distribution: keep the first occurrence only
    findings = _dedupe_missing(findings)
    final = sorted_findings(findings)
    coverage = _coverage(scanned)
    return Report(
        findings=final,
        cause_of_death=cause_of_death(final),
        coverage=coverage,
        project_types=scanned.project_types,
    )


def _dedupe_missing(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    kept: list[Finding] = []
    for f in sorted(findings, key=Finding.sort_key):
        if f.rule_id == "MISSING_DEPENDENCY":
            key = f.reason.split(" is imported", 1)[0]
            if key in seen:
                continue
            seen.add(key)
        kept.append(f)
    return kept


def _unsupported_findings(scanned: scan.ScanResult) -> list[Finding]:
    findings: list[Finding] = []
    for language, count in scanned.languages:
        if language in scan.ANALYZED_LANGUAGES:
            continue
        first = next(f.path for f in scanned.files if f.language == language)
        findings.append(
            make_finding(
                "UNSUPPORTED_LANGUAGE",
                first,
                0,
                f"{count} {language} file(s) detected; no analyzer exists, they were not checked",
            )
        )
    return findings


def _coverage(scanned: scan.ScanResult) -> tuple[tuple[str, str, int], ...]:
    rows = [
        (lang, "ANALYZED" if lang in scan.ANALYZED_LANGUAGES else "UNSUPPORTED", count)
        for lang, count in scanned.languages
    ]
    node_manifests = len(scanned.paths("node-manifest"))
    if node_manifests:
        rows.append(("package.json", "UNSUPPORTED", node_manifests))
    return tuple(sorted(rows))


def format_report(report: Report) -> str:
    """Human-readable, deterministic text rendering of an autopsy report."""
    lines = ["CAUSE OF DEATH"]
    if report.cause_of_death:
        lines.extend(f"  {cat}: {n}" for cat, n in report.cause_of_death)
    else:
        lines.append("  no failures detected by supported analyzers")
    lines.append("COVERAGE")
    lines.extend(f"  {lang}: {status} ({n} file(s))" for lang, status, n in report.coverage)
    lines.append("FINDINGS")
    for f in report.findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        lines.append(f"  [{f.severity}] [{f.repair_class}] {f.rule_id} {loc} {f.reason}")
    return "\n".join(lines) + "\n"


def report_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
