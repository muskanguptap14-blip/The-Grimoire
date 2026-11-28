# Stage 5: hook observation, dashboard Node support

## Task 27 (pytest-on-save hook): not observed, left unticked

The hook `.kiro/hooks/pytest-on-save.json` (trigger `PostFileSave`, matcher `(src|tests)[/\\].*\.py$`, command `python -m pytest -q -x`) could not be observed firing.

Blocker: this work ran in a headless sub-agent sandbox. Files are written through tool calls, not saved in the Kiro IDE editor, so no `PostFileSave` event is raised, and no hook output exists anywhere in the workspace. Nothing in the workspace is evidence of a real firing.

Static matcher check, run with Python `re.search` against the matcher from the hook file:

| Path | Matches |
| --- | --- |
| `src/grimoire/cli.py` | yes |
| `tests/unit/test_x.py` | yes |
| `tests\unit\t.py` | yes |
| `samples/sample-legacy-1/main.py` | no |
| `samples/sample-legacy-2/main.py` | no |
| `tests/frontend/lib.test.js` | no |
| `src/grimoire/dashboard/static/app.js` | no |

This only shows the matcher selects the right paths. Task 27 stays `[ ]` until someone saves a file in `src/` or `tests/` inside the Kiro IDE, sees pytest run (and a deliberately failing test show in the hook output), and saves a `samples/` file with no run.

## Dashboard Node support

- A "Node support" checkbox (`#node-check`, off by default) sits next to Scan repository. When on, the page sends `node: true` with `POST /api/autopsy` and `POST /api/runs`; when off the key is omitted. Toggling it after a scan re-runs the scan, because the autopsy depends on it. The option is built by `withOptions` in `lib.js` (unit tested).
- `server.py`: both endpoints accept an optional boolean `node` (anything else gets 400), pass it to `autopsy(node=...)` and `revive(node=...)`, and the run snapshot reports `node`. Source resolution is unchanged: hosted mode still returns 404 for unknown sample IDs and 403 for `path` or `upload`.
- `samples/sample-legacy-3` (Ember Ledger): an original Node project. `package.json` has `engines.node` `0.10.x`, renamed packages (`jade`, `node-uuid`, `coffee-script`) and bad ranges (`lodash`, `fsevents`). `index.js` prints `EMBER LEDGER ALIVE`. With Node support on, Grimoire repairs everything automatically and only `package.json` changes. `sample-legacy-1` and `-2` are unchanged.
- The diff panel already renders any patched file by path, so the `package.json` diff appears there with no extra code. It is covered by a test on the run result and a `splitDiffByFile` test.
- All new DOM text uses `textContent`; no external assets; the CSP header is unchanged.

## Node Dockerfile

- Applies only when Node support is on (`revive(node=True)`, the dashboard toggle) and the Working Copy is Node-only: a root `package.json` and no `.py` files. Everything else (Python-only, mixed, or Node support off) keeps the existing Python Dockerfile text, byte for byte.
- Output, as text only (never built, no `npm` or `docker` call):

```
FROM node:22-slim
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY . .
CMD ["node", "<main>"]
```

- `<main>` is the `main` field of the repaired `package.json`. It falls back to `index.js` when the file is unreadable, `main` is missing, not a string, empty, absolute, or contains `..`. A leading `./` is dropped. The file named by `main` is not checked for existence.
- Code: `is_node_only`, `detect_node_main`, `generate_node_dockerfile` in `src/grimoire/dockerfile.py`; the choice is made in `revive.py`. Requirements: Req 5.6 and 5.7.
- Golden files: `tests/golden/dockerfile/`. Tests are in `tests/unit/test_diffing_dockerfile.py`.

## Verification

- `python -m pytest -q`: 307 passed (299 before, 8 new: node flag, bad flag value, node run and diff, no-flag run, hosted allowlist with the flag, sample listing, sample source, static wiring).
- `node --test tests/frontend/`: 21 passed (19 before, 2 new).
- Browser check (headless Chrome, hosted mode, same method as Stage 3): selecting `sample-legacy-3` and scanning with the toggle off showed only 2 INFO findings; turning it on re-scanned and showed 7 findings (2 NODE_BAD_RANGE, 1 NODE_ENGINE_OUTDATED, 3 NODE_RENAMED_PACKAGE, 1 INFO). Requests sent: `{"sample":"sample-legacy-3"}`, then `{"sample":"sample-legacy-3","node":true}`, then `{"sample":"sample-legacy-3","prove":true,"node":true}`. The diff panel showed the 6-line `package.json` change. No console messages and no failed requests. Screenshots are in `.kiro/artifacts/screenshots/sample-legacy-3-*.png`.

## Known limitations

- The outcome for `sample-legacy-3` is PARTIAL, not SUCCESS: there is no Python entry point, so proof is UNVERIFIED ("no entry point found; nothing was run"). Grimoire never runs Node or npm (Req 10.4), so `EMBER LEDGER ALIVE` is not proven by the engine.
- The sample card says "0 Python files" for this sample.

After the Node Dockerfile step: `python -m pytest -q` 314 passed (7 new Dockerfile tests); `node --test tests/frontend/` 21 passed.

## Final evidence (Stage 5 submission pass)

Run on branch `stage4/node-manifest-modernizer`, Python 3.11 venv outside the repo.

- `python -m pytest -q`: 314 passed, 0 failed (61.9 s).
- `node --test tests/frontend/`: 21 passed, 0 failed.
- Browser check (method from [STAGE3.md](STAGE3.md): `python -m grimoire serve` plus headless Chrome driven by playwright-core, in one shell command), hosted mode, all three samples:

| | sample-legacy-1 | sample-legacy-2 | sample-legacy-3 (Node support on) |
|---|---|---|---|
| Findings | 10 | 9 | 7 (2 with Node support off) |
| Outcome | Resurrected (SUCCESS) | Resurrected (SUCCESS) | Partial recovery (PARTIAL) |
| Patched | main.py | main.py, requirements.txt | package.json |
| Proof | ALIVE, exit 0 (`TALLY KEEPER ALIVE`) | ALIVE, exit 0 (`LOST LEDGER ALIVE`) | UNVERIFIED: no entry point found; nothing was run |
| Console messages | 0 | 0 | 0 |
| Failed requests | 0 | 0 | 0 |

- Requests for sample 3: `{"sample":"sample-legacy-3"}`, `{"sample":"sample-legacy-3","node":true}`, `{"sample":"sample-legacy-3","prove":true,"node":true}`.
- The server log held only 200, 202 and 204 lines. `git status` was clean after the run (no sample was modified).
- CLI: `python -m grimoire prove samples/sample-legacy-1` exit 0 ALIVE; `prove samples/sample-legacy-2 --wheelhouse wheelhouse` exit 0 ALIVE; the unrepaired `samples/sample-legacy-1/main.py` fails with `SyntaxError` (exit 1).
- Screenshots (outside the repo): `/projects/sandbox/.kiro/artifacts/screenshots/sample-legacy-*.png`. Driver scripts: `/projects/sandbox/.kiro/artifacts/verify_dashboard.js`, `verify_node.js`.

### Not verified

- Task 27: the pytest-on-save hook was not observed firing (see above). The task stays unticked.
- `STILL_DEAD` was not produced in any run. The README demo shows the dead state as a findings count above zero plus the original `main.py` failing with a `SyntaxError`, and the revived state as zero findings plus a run that prints its `ALIVE` line.
- `sample-legacy-3` runtime behavior (`EMBER LEDGER ALIVE`) is not proven, since Node is never run.
- In the sample-legacy-2 pass the header read "Connecting / mode: unknown" because the script read it right after page load, before the health response arrived. The sample-legacy-1 pass read "mode: hosted". All API calls returned 200.

