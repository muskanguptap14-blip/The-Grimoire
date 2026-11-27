# Stage 3: Verification and cleanup

Stage 3 adds no features. It records browser verification of the dashboard on both samples, final cleanup, and known limitations. Follow-up work after the browser check (README verification, wheel checksums, spec tasks 27 and 28) is recorded under "Follow-up" below.

## Browser verification

Headless Chrome drove the dashboard in hosted mode at `http://127.0.0.1:8765/`. The header showed "mode: hosted" and "Healthy, v0.1.0, 4 offline wheels". For each sample the flow was: select the sample card, Scan repository, Resurrect with proof checked, then inspect the results, diff, Dockerfile, Validation and Proof tabs.

| | sample-legacy-1 (Tally Keeper) | sample-legacy-2 (Lost Ledger) |
|---|---|---|
| Findings | 10 (BUILTINS 2, DICT_METHODS 2, EXCEPT_AS 1, PRINT_STMT 3, OCTAL_LITERAL 1, NE_OPERATOR 1), all Error, all AUTOMATIC | 9 (OUTDATED_IMPORT 4, MISSING_DEPENDENCY 1, REMOVED_PACKAGE 2, RENAMED_PACKAGE 1, DUPLICATE_REQUIREMENT 1), 7 Error, 2 Warning, all AUTOMATIC |
| Outcome | SUCCESS, 10 before, 0 after | SUCCESS, 9 before, 0 after |
| Files patched | main.py | main.py, requirements.txt |
| Validation | 2 PASS | PASS |
| Proof | ALIVE, exit 0 ("TALLY KEEPER ALIVE", "total units: 45") | ALIVE ("LOST LEDGER ALIVE", "Harbour Accounts: 3 queued"), with a readfp DeprecationWarning |

Browser console: 0 messages, 0 page errors, 0 failed requests for both samples. All API calls returned 2xx (health, samples, autopsy 200, runs 202, run snapshot, events SSE). The server log held only 200, 202 and 204 lines. `samples/` stayed git-clean.

CLI cross-check: `grimoire prove samples/sample-legacy-N` reproduced the same diffs. Sample 1 was ALIVE. Sample 2 without `--wheelhouse` reports UNVERIFIED, because the dependencies cannot be installed offline; the dashboard uses the bundled wheelhouse, so it reports ALIVE.

## Cleanup

- No `console.log`, `TODO`, `breakpoint` or `debugger` in `src/`. Remaining `print()` calls are CLI and server output.
- `pyproject.toml` has no runtime dependencies. Dev dependencies are pytest and hypothesis, both used.
- `.gitignore` covers `__pycache__`, `.pytest_cache`, `.hypothesis` and `.venv`.

## Known limitations

- Spec task 27 stays unticked: the hook file and `pytest.ini` are verified by tests, but saving a file in an IDE to trigger the hook was not observed.
- `app.js` is checked by static tests and a few Node tests only, not by an automated browser suite.
- The offline-import test skips the dashboard.
- Origin policy: state-changing requests with a cross-origin or `null` Origin are rejected. Requests with no Origin header are allowed so the CLI and curl keep working.

## Follow-up

### README verification

Done in a fresh Python 3.11.15 venv outside the repo, then again from a clean `git clone` of branch `stage2/dashboard` with its own new venv.

- `pip install -e '.[dev]'` succeeded (network needed once, for pytest and hypothesis).
- `python -m grimoire serve` returned 200 on `/` and `{"status": "ok", "mode": "hosted", "version": "0.1.0", "wheelhouse": {"in_use": true, "wheels": 4}}` on `/api/health`. `serve --mode local` was not run in this pass.
- `prove samples/sample-legacy-1` gave ALIVE (exit 0). `prove samples/sample-legacy-2 --wheelhouse wheelhouse` gave ALIVE (exit 0). Without `--wheelhouse` it gave UNVERIFIED (exit 2).
- Clean clone: pytest 210 passed. In the original tree: pytest 210 passed, node 19 passed. Baseline before this work was 207 passed.

README inaccuracies fixed: it still said `serve` was not implemented and exited 3; it had no venv, test or Python 3.11 / `lib2to3` setup steps; it did not say sample 2 needs `--wheelhouse` to reach ALIVE.

### Wheel checksums

`wheelhouse/SHA256SUMS` holds SHA-256 for the four wheels. They match the digests PyPI reports for those versions. `sha256sum -c` passes, and `tests/unit/test_repo_config.py` checks the file against the wheels.

### Spec tasks

- Task 28 (README): ticked. Install, CLI, hosted vs local mode and the Python 3.11 / `lib2to3` constraint are documented, and following the README from a clean clone reached ALIVE on both samples.
- Task 27 (pytest-on-save): left unticked. Verified by tests: `.kiro/hooks/pytest-on-save.json` has trigger `PostFileSave`, the required matcher and command, the matcher matches `src/` and `tests/` Python files and not `samples/`, and `pytest.ini` has `testpaths = tests` with `samples` in `norecursedirs`. Not verified: that saving a file in the IDE actually runs pytest and shows failures in the hook output. That needs the Kiro IDE.
