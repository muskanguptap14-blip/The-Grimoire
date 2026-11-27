# Stage 1: Resurrection Engine

Stage 1 delivers the backend engine and CLI only. Evidence of real runs is in [STAGE1_EVIDENCE.md](STAGE1_EVIDENCE.md). The task mapping is in [../STAGE1_CHECKLIST.md](../STAGE1_CHECKLIST.md).

## Components (`src/grimoire/`)

| Module | Role |
|---|---|
| `scan.py` | Recursive scan, language and project detection, rejects symlinks that escape the repo and path traversal |
| `py2parse.py` | Python 2/3 parser facade over `lib2to3` |
| `codemods/` | One codemod per Python 2 construct (print, except, raise, backticks, `<>`, exec, octal, string prefix, builtins, dict methods) |
| `imports.py`, `data/imports_map.json` | Outdated import detection and rewrite |
| `requirements.py`, `data/packages_map.json` | requirements.txt parser and fixer (renames, removed packages, bad pins, duplicates) |
| `autopsy.py` | Findings with severity and AUTOMATIC/MANUAL repair class, Cause of Death, coverage |
| `revive.py`, `diffing.py` | Repair on an isolated temp copy, before/after reports, unified diff, backups |
| `dockerfile.py` | Dockerfile text generator (never built) |
| `verify.py` | Temp venv, offline install (`pip --no-index`), subprocess run with timeout and process-group kill |
| `cli.py`, `__main__.py` | `autopsy`, `revive`, `prove` and exit codes |

The engine has no sample-specific logic. A test greps `src/` for sample names and success lines.

## Samples

- `samples/sample-legacy-1`: Tally Keeper, a Python 2 script (print statements, `except X, e`, octal literal, `<>`, `raw_input`, `xrange`, `has_key`, `iteritems`). No dependencies.
- `samples/sample-legacy-2`: Lost Ledger, Python 2 module names (`ConfigParser`, `Queue`, `urllib2`, `StringIO`), a bad `requirements.txt` (renamed, removed and duplicate packages) and an undeclared `six` import. Recovered requirements are `beautifulsoup4` and `six`.

The spec names these `crypt_calculator` and `lost_ledger`. By user instruction the directories are `sample-legacy-1` and `sample-legacy-2`; `tasks.md`, `design.md` and `structure.md` were updated with this note.

Sample 2 reaches ALIVE only with a wheelhouse that holds `beautifulsoup4` and `six`. The integration tests build tiny local wheels with `zipfile` and the verifier really runs `pip install --no-index` and the entry point. Without a wheelhouse the result is UNVERIFIED by design.

## Run the backend

    pip install -e ".[dev]"
    python -m grimoire autopsy PATH [--json]
    python -m grimoire revive PATH [--output DIR] [--json]
    python -m grimoire prove PATH [--output DIR] [--wheelhouse DIR] [--timeout SECONDS] [--json]

Exit codes: 0 ALIVE or no remaining findings, 1 STILL_DEAD or TIMED_OUT, 2 UNVERIFIED, 3 error.

## Test both samples

    python -m pytest -q
    python -m pytest -q tests/integration/test_samples.py
    python -m grimoire revive samples/sample-legacy-1 --output /tmp/out1
    python -m grimoire revive samples/sample-legacy-2 --output /tmp/out2
    python -m grimoire prove samples/sample-legacy-1
    python -m grimoire prove samples/sample-legacy-2 --wheelhouse WHEELHOUSE_DIR

`WHEELHOUSE_DIR` must contain wheels for `beautifulsoup4` and `six`. See `build_wheel` in `tests/integration/test_samples.py` for a stdlib-only way to build them.

## Known limitations

- Needs Python 3.11 (`lib2to3`, removed in 3.13).
- The verifier only supports POSIX venv layout (`bin/python`).
- Dependencies are never downloaded. Projects with third-party requirements give UNVERIFIED without a wheelhouse.
- The proof run is not network-isolated or sandboxed. It uses a temp copy, a temp venv, a minimal environment, a timeout and a process-group kill, but the repository's code can still reach the network and any file the user can read. `pip --no-index` only constrains pip. Run `prove` only on repositories you trust.
- Only Python repositories are handled. Node support (spec task 29) is skipped.
- Mapping tables are small and static; unknown packages and imports are left for manual review.
- `readfp` in sample 2 still works on 3.11 but is removed in 3.12; Grimoire does not rewrite it.
- The recovered project is validated by compiling and running its entry point, not by running its own tests.

## Resolve before Stage 2

- Implement `serve` and the dashboard (spec tasks 25 and 26). `serve` currently exits with code 3.
- Decide how the hosted demo gets wheels for sample 2 (ship a wheelhouse or run it as UNVERIFIED).
- Decide whether to keep the user override sample names or restore the spec names.
- Task 27 (pytest-on-save hook file) and the hosted/local README sections of task 28 are not verified.
- Hypothesis is a dev dependency; `tech.md` already lists it.

Stage 2 resolved the first three items (see [STAGE2.md](STAGE2.md)). The task 27 and 28 item is deferred to Stage 3.
