# Stage 1 Checklist

Maps the Stage 1 brief to the tasks in `.kiro/specs/grimoire-core/tasks.md`.
Sample directories are `samples/sample-legacy-1` and `samples/sample-legacy-2` (user override of the spec names).
Frontend, dashboard and the `serve` command are Stage 2. The Node stretch (task 29) is skipped.

## Foundation and engine (FEAT-001)
- [x] Tasks 1-3: `pyproject.toml`, package skeleton, `tests/conftest.py` with `ci` and `dev` Hypothesis profiles, `.gitignore`
- [x] Task 2: frozen models with severity and automatic/manual repair class (`models.py`)
- [x] Task 4: recursive scan, language and project detection, symlink and traversal rejection (`scan.py`)
- [x] Task 5: Python 2/3 parser facade (`py2parse.py`)
- [x] Tasks 6-12: property strategies, ten codemods, pipeline with `PATCH_REJECTED` path (`codemods/`)
- [x] Tasks 13-14: imports table and rewriter (`imports.py`, `data/imports_map.json`)
- [x] Tasks 15-16: requirements parser, fixer and packages table (`requirements.py`, `data/packages_map.json`)
- [x] Task 17: autopsy: syntax, AST imports, broken imports, missing dependencies, manifests, Cause of Death, unsupported coverage (`autopsy.py`)

## Resurrection pipeline (FEAT-002)
- [ ] Task 19: `revive` on an isolated working copy, backups, before/after reports, diff (`diffing.py`)
- [ ] Task 20: Dockerfile text generator (`dockerfile.py`)
- [ ] Task 21: verifier with offline venv, timeout, process-group kill (`verify.py`)
- [ ] Task 22: offline guarantee test with sockets blocked
- [ ] Task 23: CLI `autopsy`, `revive`, `prove` with exit codes (`cli.py`, `__main__.py`)

## Samples and completion (FEAT-003)
- [ ] Task 18: `samples/sample-legacy-1` and `samples/sample-legacy-2` with READMEs, documented failures, expected outcomes
- [ ] Task 24: end-to-end test, both samples STILL_DEAD before and ALIVE after, idempotent revive
- [ ] Backup safety and error handling tests for the pipeline
- [ ] Task 28: README: components, known limitations, exact run and test commands
- [ ] Final architecture review and full test run
