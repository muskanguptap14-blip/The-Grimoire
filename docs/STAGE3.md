# Stage 3: Verification and cleanup

Stage 3 adds no features. It records browser verification of the dashboard on both samples, final cleanup, and known limitations. Spec tasks 27 (pytest-on-save hook) and 28 (README and demo script) remain unticked.

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

- The bundled wheels have no checksum file, so wheel integrity is not verified.
- `app.js` is checked by static tests and a few Node tests only, not by an automated browser suite.
- The offline-import test skips the dashboard.
- Origin policy: state-changing requests with a cross-origin or `null` Origin are rejected. Requests with no Origin header are allowed so the CLI and curl keep working.
