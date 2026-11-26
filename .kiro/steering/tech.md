# Grimoire: Tech

## Stack
- Python 3.11 (pinned: the Python 2 parser depends on `lib2to3`, which is removed in 3.13).
- Tests: `pytest`, `hypothesis`.
- Runtime dependencies: standard library only, where possible. Dev dependencies: pytest, hypothesis.
- Dashboard: stdlib `http.server` plus static HTML/CSS/JS. No frameworks, no CDN.

## Python 2 parsing
`ast.parse` cannot read Python 2. Use `lib2to3` (`pgen2` driver with the Python 2 grammar, print statement enabled) to build a lossless concrete syntax tree. Codemods transform that tree, and the result is validated with `ast.parse`. See `design.md`.

## Determinism rules
- Sort every file listing, dict iteration and report entry.
- No timestamps, random values or absolute paths in output artifacts. Paths are repo-relative with `/` separators.
- Read and write files as UTF-8 with explicit `newline` handling. Preserve the original line endings.

## No network at runtime
- No `requests`, `urllib.request`, sockets or `pip` index access in engine code.
- Dependency fixes come from data tables, not lookups.
- Verification creates the venv with `python -m venv` and installs only from a local wheelhouse (`pip install --no-index --find-links`). If a package is not available locally, report it as `unverified`. Never fall back to the network.
- A test asserts that sockets are blocked during an engine run.

## Subprocess safety
- Run with `subprocess.run([...], shell=False, timeout=..., cwd=<temp copy>, env=<minimal env>)`.
- Kill the whole process group on timeout and report `TIMED_OUT`.
- Cap captured output size.

## Commands
- Install dev deps: `pip install -e ".[dev]"`
- Test: `pytest -q`
- CLI: `python -m grimoire <autopsy|revive|prove|serve> <path>`
