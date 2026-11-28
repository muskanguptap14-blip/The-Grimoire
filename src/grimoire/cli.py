"""Command line interface: a thin shell over the pipeline.

Exit codes: 0 ALIVE (or clean), 1 STILL_DEAD/TIMED_OUT, 2 UNVERIFIED, 3 internal error.
``serve`` starts the dashboard (3 on a configuration or bind error).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import autopsy as autopsy_mod
from . import revive as revive_mod
from . import verify
from .models import Report

EXIT_OK, EXIT_DEAD, EXIT_UNVERIFIED, EXIT_ERROR = 0, 1, 2, 3
NODE_HELP = "also analyze and repair package.json manifests (offline, no npm, JavaScript sources untouched)"


def format_revive(report: Report) -> str:
    lines = ["BEFORE"]
    lines.extend(_finding_lines(report.before_findings))
    lines.append("REPAIRS APPLIED")
    if report.patches:
        lines.extend(f"  {p.path}: {', '.join(p.rules_applied)}" for p in report.patches)
    else:
        lines.append("  none")
    lines.append("REPAIRS REJECTED")
    rejected = [f for f in report.findings if f.rule_id == "PATCH_REJECTED"]
    lines.extend(_finding_lines(tuple(rejected)))
    lines.append("REMAINING (manual or unsupported)")
    lines.extend(_finding_lines(report.findings))
    lines.append("VALIDATION")
    lines.extend(f"  {s}: {name}" + (f" ({detail})" if detail else "") for name, s, detail in report.validation)
    if report.proof is not None:
        lines.append(f"PROOF: {report.proof.status}")
        lines.extend(f"  {line}" for line in report.proof.log_lines)
    if report.diff:
        lines.append("DIFF")
        lines.append(report.diff.rstrip("\n"))
    return "\n".join(lines) + "\n"


def _finding_lines(findings) -> list[str]:
    if not findings:
        return ["  none"]
    out = []
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        out.append(f"  [{f.severity}] [{f.repair_class}] {f.rule_id} {loc} {f.reason}")
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grimoire", description="Deterministic resurrection engine")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("autopsy", help="diagnose a repository (read only)")
    p.add_argument("repo")
    p.add_argument("--json", action="store_true")
    p.add_argument("--node", action="store_true", help=NODE_HELP)
    for name, helptext in (("revive", "repair an isolated copy and report"), ("prove", "revive, then run the result offline")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("repo")
        p.add_argument("--json", action="store_true")
        p.add_argument("--node", action="store_true", help=NODE_HELP)
        p.add_argument("--output", "--apply", dest="output", metavar="DIR", help="write the revived copy to a new directory outside the repo")
        if name == "prove":
            p.add_argument("--wheelhouse", help="directory of wheels for offline installs")
            p.add_argument("--timeout", type=float, default=verify.DEFAULT_TIMEOUT)
    p = sub.add_parser("serve", help="start the dashboard")
    p.add_argument("--mode", choices=("hosted", "local"), default="hosted", help="hosted: bundled samples only; local: also paths and uploads")
    p.add_argument("--host", default="127.0.0.1", help="bind address (local mode requires loopback)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--wheelhouse", help="directory of wheels for offline proof installs (default: repo wheelhouse/)")
    p.add_argument("--samples-dir", help="directory of sample repositories (default: repo samples/)")
    return parser


def _proof_exit(report: Report) -> int:
    status = report.proof.status if report.proof else "UNVERIFIED"
    return {"ALIVE": EXIT_OK, "STILL_DEAD": EXIT_DEAD, "TIMED_OUT": EXIT_DEAD}.get(status, EXIT_UNVERIFIED)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse usage errors
        return EXIT_ERROR if exc.code not in (0, None) else EXIT_OK
    try:
        if args.command == "serve":
            from .dashboard.server import Config, serve

            return serve(
                Config(
                    mode=args.mode,
                    host=args.host,
                    port=args.port,
                    wheelhouse=Path(args.wheelhouse) if args.wheelhouse else None,
                    samples_dir=Path(args.samples_dir) if args.samples_dir else None,
                )
            )
        if args.command == "autopsy":
            report = autopsy_mod.autopsy(args.repo, node=args.node)
            sys.stdout.write(autopsy_mod.report_json(report) if args.json else autopsy_mod.format_report(report))
            return EXIT_ERROR if any(f.rule_id == "INVALID_REPO" for f in report.findings) else EXIT_OK
        report = revive_mod.revive(
            args.repo,
            args.output,
            prove=args.command == "prove",
            node=args.node,
            wheelhouse=getattr(args, "wheelhouse", None),
            timeout=getattr(args, "timeout", verify.DEFAULT_TIMEOUT),
        )
        if any(f.rule_id == "INVALID_REPO" for f in report.findings):
            sys.stdout.write(autopsy_mod.report_json(report) if args.json else autopsy_mod.format_report(report))
            return EXIT_ERROR
        sys.stdout.write(autopsy_mod.report_json(report) if args.json else format_revive(report))
        if args.command == "prove":
            return _proof_exit(report)
        return EXIT_DEAD if any(f.severity != "INFO" for f in report.findings) else EXIT_OK
    except revive_mod.OutputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # internal error: never a traceback-driven exit code
        print(f"internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
