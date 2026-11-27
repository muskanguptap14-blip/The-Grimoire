# Stage 2: Dashboard and integration

Stage 2 adds a local web dashboard and an HTTP API on top of the Stage 1 engine. The server uses only the Python standard library. The UI is plain HTML, CSS and JavaScript with no frameworks, no CDN and no external requests. Spec tasks 25 (dashboard server) and 26 (dashboard UI) are done. Spec tasks 27 (pytest-on-save hook) and 28 (README and demo script) are deferred to Stage 3.

Sample names are unchanged: `samples/sample-legacy-1` and `samples/sample-legacy-2`.

## Run it

```
pip install -e '.[dev]'
python -m grimoire serve                 # hosted mode, http://127.0.0.1:8765/
python -m grimoire serve --mode local    # also scan a path or upload a zip
```

Options: `--mode {hosted,local}`, `--host` (local mode requires a loopback address), `--port` (default 8765), `--wheelhouse DIR` (default: repo `wheelhouse/`), `--samples-dir DIR` (default: repo `samples/`). `serve` exits 3 on a configuration or bind error. Ctrl-C and SIGTERM shut the server down and remove its temp directory.

## Implemented screens

One page, `src/grimoire/dashboard/static/index.html`, with these panels:

| Panel | What it shows | Data source |
|---|---|---|
| Header | Mode badge (hosted or local), health dot | `GET /api/health` |
| Repository | Sample cards with file lists. Local mode adds a path input and a zip drop zone with validation messages. Hosted mode shows an explanation instead | `GET /api/samples` |
| Autopsy overview | Stat tiles, severity chart, ranked Cause of Death bars, language coverage | `POST /api/autopsy` |
| Detected issues | Findings table: severity, rule, location, reason, repair class. Filters (severity, category, class), text search, sortable columns, empty state | `POST /api/autopsy` |
| Recovery plan | Findings grouped by rule with count, files, action and AUTOMATIC or MANUAL tag. Pipeline visual whose nodes follow real stage events. Include-proof checkbox and a caution | `POST /api/autopsy`, stage events |
| Live progress | Stage timeline with real durations, SSE log console, auto-scroll toggle, copy log | `GET /api/runs/<id>/events` |
| Results | Outcome banner (SUCCESS, PARTIAL, FAILURE) with reason, before and after stats and bars, patched files | `GET /api/runs/<id>` |
| Repair detail | Per-file diff with +/- coloring and rules, before and after toggle, Dockerfile, Validation and Proof tabs, JSON report download | run result |
| Error banner | Keeps the app usable and offers Retry and Dismiss | any failed request |

The page is responsive from 360 px to wide desktop, respects `prefers-reduced-motion`, has focus rings and aria-live regions for progress and outcome. All text is inserted with `textContent` (a test forbids `innerHTML` and similar APIs).

## API reference

All responses are JSON unless noted. Errors are `{"error": "<code>", "detail": "<text>"}`. Every response carries `Content-Security-Policy: default-src 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `Cache-Control: no-store`.

| Route | Request | Success response |
|---|---|---|
| `GET /` and static files | none. Only `index.html`, `app.css`, `app.js`, `lib.js` are served. `/favicon.ico` returns 204 | file |
| `GET /api/health` | none | `{status, mode, version, wheelhouse: {in_use, wheels}}` |
| `GET /api/samples` | none | `{samples: [{id, title, files: [{path, size}], python_files}]}`, built from the samples directory |
| `POST /api/autopsy` | JSON with exactly one of `sample`, `path`, `upload` | 200 `{source, summary, findings, cause_of_death, plan}`. `summary` holds `files_by_language`, `project_types`, `coverage` and `counts` (`total`, `severity`, `category`, `repair_class`). Each `plan` item is `{rule_id, category, severity, repair_class, count, files, action}` |
| `POST /api/runs` | JSON with exactly one source key, plus optional `prove` (boolean, default true) | 202 `{run_id}` |
| `GET /api/runs/<id>` | none | `{run_id, state, source, prove, stages, events, result}`. `state` is `queued`, `running`, `done` or `error`. Each stage is `{name, status, message, duration_s}` |
| `GET /api/runs/<id>/events` | optional `Last-Event-ID` header | `text/event-stream`. Events have an increasing `id` and a `type` of `state`, `stage`, `log`, `error` or `end`. Past events replay first, then live ones. The stream ends after `end` |
| `POST /api/upload` | body `application/zip` (local mode only) | 201 `{upload_id}` |

Stages, in order: `autopsy`, `copy`, `repair`, `reanalyze`, `validate`, `dockerfile`, `prove` (the last is omitted when `prove` is false).

The `result` object has `outcome`, `reason`, `stats`, `before` and `after` (`findings`, `counts`), `patches` (`path`, `rules`, `before`, `after`), `diff`, `dockerfile`, `validation`, `proof` (`status`, `exit_code`, `log_lines`, or null), `cause_of_death`, `coverage`, `project_types`. `stats` is `{issues_before, issues_after, automatic_fixed, manual_remaining, files_scanned, files_patched}`, computed only from the engine report. `automatic_fixed` is the number of AUTOMATIC-class findings before repair minus the number still present after repair (never below 0), so it is a before/after difference and not a count of individual edits. Outcome rules: SUCCESS means proof ALIVE and no non-INFO findings left. PARTIAL means repairs applied but the proof was UNVERIFIED or not requested, or findings remain. FAILURE means STILL_DEAD, TIMED_OUT, an invalid repository or an internal error.

Error codes:

| Status | Codes |
|---|---|
| 400 | `bad_json`, `bad_request`, `invalid_path`, `bad_zip`, `unsafe_path`, `symlink` |
| 403 | `forbidden` (path or upload in hosted mode), `bad_host`, `bad_origin` |
| 404 | `not_found`, `unknown_sample`, `unknown_upload`, `unknown_run` |
| 411 | `length_required` |
| 413 | `too_large`, `too_many_files` |
| 415 | `unsupported_media_type` |
| 429 | `too_many_runs` (limit 4 active runs) |
| 501 | unsupported HTTP method |

## Backend integration per control

| Control | Calls | Engine function |
|---|---|---|
| Sample cards | `GET /api/samples` | directory listing of `samples/` |
| Scan repository | `POST /api/autopsy` | `autopsy.autopsy` |
| Use path (local) | `POST /api/autopsy` with `path` | `autopsy.autopsy` |
| Zip upload (local) | `POST /api/upload`, then `upload` source | safe extraction, then `autopsy.autopsy` |
| Resurrect | `POST /api/runs`, then SSE | `revive.revive(..., on_event, on_line)` |
| Include proof | `prove` field | `verify.verify` with the wheelhouse |
| Download report | none, built in the browser from the result | n/a |

The engine hooks added for this are additive and default to None: `revive(on_event, on_line)` and `verify(on_line)`. `on_line` forwards only the entry-point run output, not the venv or pip output.

## Working workflows

1. Select a sample, press Scan. The autopsy, findings table and recovery plan fill in.
2. Press Resurrect. The timeline and log stream live over SSE. If `EventSource` fails, the UI polls `GET /api/runs/<id>`.
3. Review the outcome banner, stats, patched files, diff, Dockerfile, validation rows and proof log. Download the JSON report.
4. Hosted mode (default): only bundled samples run. Path and upload requests get 403.
5. Local mode: also accepts a directory path or a zip upload (max 50 MB, 5000 files; absolute paths, `..` and symlinks are rejected).

## Wheelhouse

Sample 2 declares `beautifulsoup4`, which needs wheels to install without network access. `wheelhouse/` ships four real wheels (beautifulsoup4, soupsieve, six, typing_extensions) so the proof step can run `pip install --no-index --find-links wheelhouse`. With it, both samples reach SUCCESS with proof ALIVE. Without it (`wheelhouse=None`), sample 2 gives PARTIAL with proof UNVERIFIED. See `wheelhouse/README.md` for licenses (typing_extensions is PSF-2.0). The server health route reports whether a wheelhouse is in use.

## Security model

- Hosted mode accepts bundled sample ids only. Unknown ids get 404, paths and uploads get 403.
- Local mode refuses non-loopback `--host`.
- The Host header is validated (DNS rebinding) and POSTs with a cross-origin `Origin` (including `null`) are rejected. A POST with no `Origin` header is accepted so that curl, the CLI and test clients work; browsers always send `Origin` on cross-origin POSTs, so this does not open a browser CSRF path. POST needs `Content-Type: application/json` (or `application/zip` for upload). JSON bodies are capped at 64 KB.
- Static serving uses a file-name allowlist, so path traversal returns 404.
- The 50 most recent runs are kept. Uploads live in a per-server temp directory removed on shutdown. Samples are never written (runs use a temp copy).
- Tracebacks go to the server's stderr, never to clients.
- **Caveat: `prove` is not sandboxed.** It runs the repaired project's entry point with a temp venv, minimal environment, timeout and process-group kill, but the code can still reach the network and any file the server user can read. For this reason hosted mode runs bundled samples only. In local mode, only scan or run repositories you trust.
- `tests/unit/test_offline.py` still asserts that the engine imports no network modules. The dashboard package is excluded from that check because it imports `socket` to listen.

## Browser verification

A Playwright browser tool (headless Chromium) was available and used.

- FEAT-003 (local mode, port 8765): sample select, scan, filter, resurrect, SSE progress, both samples SUCCESS with proof ALIVE, diff, Dockerfile, validation and proof tabs, and a fix for a 360 px horizontal overflow.
- FEAT-004 (hosted mode, the default, port 8791): loaded the page, confirmed the mode badge read "mode: hosted" and the hosted note was shown. Then, for each sample in turn, clicked its card, Scan, and Resurrect. Both ended with "Resurrected (SUCCESS)" and proof "ALIVE, exit code 0". The stat tiles showed 10 issues before and 0 after for sample 1 and 9 before and 0 after for sample 2. All seven stages showed done. The first run showed a `/favicon.ico` 404 in the console. The server now answers 204, and a reload produced no console entries. The server log showed only 200, 202 and 204 responses and no tracebacks.
- Not exercised in a browser: zip upload and drag and drop, the SSE polling fallback, and the hosted-mode 403 states through the UI (the 403 was checked with curl and in tests). Screenshots and page snapshots are stored under the sandbox's `.kiro/artifacts/screenshots/`, outside the repository, and are not committed.
- The headless sandbox lacks fonts for the unicode severity and status icons (they render as boxes there). Text labels always accompany them.

Results in the browser match the backend: see `docs/STAGE2_EVIDENCE.md`, where the same counts come from the HTTP API and are asserted equal to direct engine calls in `tests/dashboard/test_e2e_samples.py`.

## Tests

- `../.venv/bin/python -m pytest -q`: 207 passed (204 earlier, plus 3 regression tests for the Origin check, the bounded output read and the offline check).
- `node --test tests/frontend/`: 19 passed.
- Dev server check: `python -m grimoire serve` (no port flag) printed `Grimoire dashboard (hosted mode): http://127.0.0.1:8765/`. `GET /api/health` returned 200 `{"status": "ok", "mode": "hosted", "version": "0.1.0", "wheelhouse": {"in_use": true, "wheels": 4}}`. `GET /api/samples` listed `sample-legacy-1` and `sample-legacy-2`.

## Remaining limitations

- `prove` is not sandboxed (see above). Treat local mode as trusted-user only.
- Wheelhouse content is fixed to the packages the samples need. Other projects with third-party requirements give UNVERIFIED unless you pass `--wheelhouse`.
- Run state is in memory. Restarting the server loses runs. Only 50 runs are kept.
- The live log is capped at 2000 events per run. Later lines appear in the final result.
- No authentication. The server is intended for localhost.
- Zip upload, drag and drop and the SSE polling fallback have unit or API coverage but no browser check.
- Python repositories only. Node support (spec task 29) is skipped.

## Stage 3 pointers

- Spec task 27: pytest-on-save hook verification.
- Spec task 28: README demo script, including hosted vs local sections. Only a short `serve` section was added in Stage 2.
- Consider real isolation for `prove` (container or network namespace) before any public hosting.
