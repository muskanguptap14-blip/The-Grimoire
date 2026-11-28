# Stage 2 Evidence

Captured on branch `stage2/dashboard`. Everything below was run in this sandbox. Python 3.11 venv, Node v22.

## Test suites

```
$ ../.venv/bin/python -m pytest -q
204 passed in 54.48s

$ node --test tests/frontend/
# tests 19
# pass 19
# fail 0
```

## Served app, both samples through the HTTP API

The server was started in hosted mode (the default) on a spare local port. Start line:

```
Grimoire dashboard (hosted mode): http://127.0.0.1:8792/
```

Health:

```
{"status": "ok", "mode": "hosted", "version": "0.1.0", "wheelhouse": {"in_use": true, "wheels": 4}}
```

Each sample was started with `POST /api/runs {"sample": ...}` and read back with `GET /api/runs/<id>`:

```
sample: sample-legacy-1 state: done
outcome: SUCCESS | the repaired project ran offline and exited 0 with no findings remaining
stats: {"issues_before": 10, "issues_after": 0, "automatic_fixed": 10, "manual_remaining": 0, "files_scanned": 1, "files_patched": 1}
proof: ALIVE exit 0
patched: ['main.py']
validation: [('all Python files parse', 'PASS'), ('no unresolved findings', 'PASS')]
log tail: ['bad input gives 0', 'report mode: 755', 'TALLY KEEPER ALIVE']
sample: sample-legacy-2 state: done
outcome: SUCCESS | the repaired project ran offline and exited 0 with no findings remaining
stats: {"issues_before": 9, "issues_after": 0, "automatic_fixed": 9, "manual_remaining": 0, "files_scanned": 1, "files_patched": 2}
proof: ALIVE exit 0
patched: ['main.py', 'requirements.txt']
validation: [('all Python files parse', 'PASS'), ('no unresolved findings', 'PASS')]
log tail: ['Harbour Accounts: 3 queued', 'network error check: False', 'LOST LEDGER ALIVE']
hosted path request status: 403
```

Server log for that session (no errors, no tracebacks):

```
grimoire dashboard: "GET /api/health HTTP/1.1" 200 -
grimoire dashboard: "POST /api/runs HTTP/1.1" 202 -
grimoire dashboard: "GET /api/runs/<id> HTTP/1.1" 200 -
grimoire dashboard: "POST /api/runs HTTP/1.1" 202 -
grimoire dashboard: "GET /api/runs/<id> HTTP/1.1" 200 -
grimoire dashboard: "POST /api/runs HTTP/1.1" 403 -
shutting down
```

Samples unchanged: `git status --short samples/` printed nothing after the runs.

## Browser check (hosted mode)

Playwright headless Chromium against the default hosted server. The page reported "mode: hosted". Selecting each sample card, pressing Scan and then Resurrect gave:

| Sample | Findings rows after scan | Outcome | Stats (before, after, fixed, manual, scanned, patched) | Proof | Stages |
|---|---|---|---|---|---|
| sample-legacy-1 | 10 | Resurrected (SUCCESS) | 10, 0, 10, 0, 1, 1 | ALIVE, exit code 0 | 7 of 7 done |
| sample-legacy-2 | 9 | Resurrected (SUCCESS) | 9, 0, 9, 0, 1, 2 | ALIVE, exit code 0 | 7 of 7 done |

These match the API output above. After the favicon fix (204), page load produced no console messages. Not exercised in the browser: zip upload, drag and drop, the SSE polling fallback. See `docs/STAGE2.md`.

## Equality with the engine

`tests/dashboard/test_e2e_samples.py` asserts, for both samples, that the HTTP API's findings counts (scan, before and after), patched file paths, diff and proof status equal the direct `autopsy.autopsy` and `revive.revive(prove=True, wheelhouse=...)` results, that the proof log contains the success line, and that the sample tree hash is unchanged.
