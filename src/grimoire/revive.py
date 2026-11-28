"""Resurrection pipeline: repair an isolated Working Copy, re-analyze, validate, report.

The source repository is never modified. With ``output`` the revived copy is written to a
new directory outside the source, together with backups of every original file that changed.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from . import autopsy as autopsy_mod
from . import codemods, diffing, dockerfile, nodejs, requirements, scan, verify
from .models import FilePatch, Finding, Report, make_finding, sorted_findings

BACKUP_DIR = ".grimoire-backup"
DOCKERFILE_NAME = "Dockerfile.grimoire"
DOCKERIGNORE_NAME = ".dockerignore"
_MISSING_DIST = re.compile(r"but (?P<dist>\S+) is not declared")


class OutputError(ValueError):
    """The requested output directory is unsafe."""


def _copy_working_copy(src: str, dst: str) -> None:
    """Copy regular files (no symlinks, no ignored directories) preserving relative layout."""
    verify.copy_tree(src, dst)


def _check_output(source: str, output: str) -> str:
    src = Path(source).resolve()
    out = Path(output).resolve()
    if out == src or src in out.parents or out in src.parents:
        raise OutputError("output directory must be outside the source repository and must not contain it")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise OutputError("output directory already exists and is not empty; refusing to overwrite")
    return str(out)


def _write(root: str, rel: str, text: str, encoding: str, originals: dict[str, bytes]) -> None:
    path = scan.resolve_in_repo(root, rel)
    originals.setdefault(rel, path.read_bytes())
    path.write_bytes(text.encode(encoding))


def _repair(
    work: str, before: tuple[Finding, ...], originals: dict[str, bytes], node: bool = False
) -> tuple[list[FilePatch], list[Finding]]:
    """Apply every automatic repair to the working copy. Returns patches and rejection findings."""
    scanned = scan.scan_repo(work)
    patches: list[FilePatch] = []
    rejected: list[Finding] = []

    for path in scanned.paths("python"):
        src, err = scan.read_source(work, path)
        if src is None:
            continue  # autopsy already reports the unreadable file
        result = codemods.apply_all(src.text, path)
        rejected.extend(f for f in result.findings if f.rule_id == "PATCH_REJECTED")
        if result.patch is not None:
            try:
                result.patch.after.encode(src.encoding)
            except UnicodeEncodeError:
                rejected.append(
                    make_finding("PATCH_REJECTED", path, 0, f"patched output cannot be encoded as {src.encoding}; original kept")
                )
                continue
            _write(work, path, result.patch.after, src.encoding, originals)
            patches.append(result.patch)

    missing = sorted(
        {
            m.group("dist")
            for f in before
            if f.rule_id == "MISSING_DEPENDENCY" and f.repair_class == "AUTOMATIC"
            for m in [_MISSING_DIST.search(f.reason)]
            if m
        }
    )
    for path in scanned.paths("requirements"):
        src, err = scan.read_source(work, path)
        if src is None:
            continue
        text, _findings = requirements.fix_requirements(src.text, path)
        if path == "requirements.txt" and missing:
            text = requirements.add_requirements(text, missing)
        if text != src.text:
            _write(work, path, text, src.encoding, originals)
            patches.append(FilePatch(path, src.text, text, ("REQUIREMENTS",)))

    if node:
        for path in scanned.paths("node-manifest"):
            src, err = scan.read_source(work, path)
            if src is None:
                continue
            text, node_findings = nodejs.fix_manifest(src.text, path)
            if text != src.text:
                rules = tuple(sorted({f.rule_id for f in node_findings if f.repair_class == "AUTOMATIC"}))
                _write(work, path, text, src.encoding, originals)
                patches.append(FilePatch(path, src.text, text, rules))
    return patches, rejected


def _manifest_failures(work: str) -> list[str]:
    failures: list[str] = []
    for path in scan.scan_repo(work).paths("node-manifest"):
        src, err = scan.read_source(work, path)
        if src is None:
            failures.append(f"{path}: {err.reason if err else 'unreadable'}")
            continue
        _data, error = nodejs.parse_manifest(src.text)
        if error:
            failures.append(f"{path}: {error}")
    return failures


def _validate(work: str, after: Report, node: bool = False) -> tuple[tuple[str, str, str], ...]:
    failures = verify.compile_check(work)
    remaining = [f for f in after.findings if f.severity != "INFO"]
    rows = [("all Python files parse", "FAIL" if failures else "PASS", "; ".join(failures))]
    if node:
        bad = _manifest_failures(work)
        rows.append(("all package.json files parse", "FAIL" if bad else "PASS", "; ".join(bad)))
    rows.append(
        (
            "no unresolved findings",
            "FAIL" if remaining else "PASS",
            f"{len(remaining)} finding(s) remain" if remaining else "",
        )
    )
    return tuple(rows)


def _persist(
    work: str, output: str, originals: dict[str, bytes], dockerfile_text: str, dockerignore_text: str = ""
) -> None:
    # _check_output already guarantees output is absent or an empty directory.
    existed = os.path.isdir(output)
    try:
        shutil.copytree(work, output, dirs_exist_ok=True)
        for rel in sorted(originals):
            backup = Path(output) / BACKUP_DIR / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(originals[rel])
        (Path(output) / DOCKERFILE_NAME).write_text(dockerfile_text, encoding="utf-8")
        if dockerignore_text:
            (Path(output) / DOCKERIGNORE_NAME).write_text(dockerignore_text, encoding="utf-8")
    except BaseException:
        # Do not leave a partial output that would block a retry.
        if existed:
            for child in Path(output).iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        else:
            shutil.rmtree(output, ignore_errors=True)
        raise


def revive(
    repo: str | os.PathLike[str],
    output: str | os.PathLike[str] | None = None,
    *,
    prove: bool = False,
    node: bool = False,
    wheelhouse: str | os.PathLike[str] | None = None,
    timeout: float = verify.DEFAULT_TIMEOUT,
    on_event: Callable[[str, str, str], None] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> Report:
    """Repair a repository in an isolated copy and report before and after.

    Raises OutputError when ``output`` is unsafe. Everything else becomes a Finding.
    ``node`` also analyzes and repairs package.json manifests (never JavaScript sources).
    ``on_event(stage, status, message)`` and ``on_line(line)`` are optional observers
    (status is "start" or "done"); they never change the result.
    """
    def emit(stage: str, status: str, message: str = "") -> None:
        if on_event is not None:
            on_event(stage, status, message)

    source = os.fspath(repo)
    out_path = _check_output(source, os.fspath(output)) if output is not None else None

    emit("autopsy", "start", "diagnosing the repository")
    before = autopsy_mod.autopsy(source, node=node)
    emit("autopsy", "done", f"{len(before.findings)} finding(s)")
    if any(f.rule_id == "INVALID_REPO" for f in before.findings):
        return before

    tmp = tempfile.mkdtemp(prefix="grimoire-revive-")
    try:
        work = os.path.join(tmp, "work")
        emit("copy", "start", "copying into an isolated working copy")
        _copy_working_copy(source, work)
        emit("copy", "done", "working copy ready")
        originals: dict[str, bytes] = {}
        emit("repair", "start", "applying automatic repairs")
        patches, rejected = _repair(work, before.findings, originals, node)
        emit("repair", "done", f"{len(patches)} file(s) patched")
        emit("reanalyze", "start", "re-running analysis on the repaired copy")
        after = autopsy_mod.autopsy(work, node=node)
        findings = sorted_findings(list(after.findings) + rejected)
        emit("reanalyze", "done", f"{len(findings)} finding(s) remain")
        emit("validate", "start", "validating the repaired copy")
        validation = _validate(work, after, node)
        emit("validate", "done", ", ".join(f"{n}: {s}" for n, s, _d in validation))
        emit("dockerfile", "start", "generating Dockerfile")
        entry = dockerfile.detect_entry(work)
        has_req = os.path.isfile(os.path.join(work, "requirements.txt"))
        dockerignore = ""
        if node and dockerfile.is_node_only(work):
            docker = dockerfile.generate_node_dockerfile(dockerfile.detect_node_main(work))
            dockerignore = dockerfile.generate_node_dockerignore()
        else:
            docker = dockerfile.generate_dockerfile(entry, has_req)
        emit("dockerfile", "done", "Dockerfile generated (never built or run)")

        proof = None
        if prove:
            emit("prove", "start", "running the repaired project offline")
            blocking = [f for f in findings if f.severity != "INFO"]
            if blocking:
                proof = verify.ProofResult(
                    "STILL_DEAD",
                    None,
                    (f"{len(blocking)} finding(s) remain after repair; project was not run",),
                )
            else:
                proof = verify.verify(work, entry, wheelhouse=wheelhouse, timeout=timeout, on_line=on_line)
                if proof.status == "ALIVE" and any(f.category == "UNSUPPORTED" for f in findings):
                    proof = verify.ProofResult(
                        "UNVERIFIED",
                        proof.exit_code,
                        proof.log_lines + ("the entry ran but unsupported parts of the repository were not checked",),
                    )
            emit("prove", "done", f"proof: {proof.status}")

        if out_path is not None:
            _persist(work, out_path, originals, docker, dockerignore)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    patches.sort(key=lambda p: p.path)
    return Report(
        findings=findings,
        cause_of_death=autopsy_mod.cause_of_death(findings),
        patches=tuple(patches),
        diff=diffing.unified_diff(patches),
        dockerfile=docker,
        proof=proof,
        coverage=after.coverage,
        project_types=after.project_types,
        before_findings=before.findings,
        validation=validation,
        dockerignore=dockerignore,
    )
