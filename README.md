# Grimoire

Grimoire is a deterministic software-archaeology and resurrection engine, built for the Kiroween Resurrection category.

It takes a dead repository and does three things:

1. **Autopsy.** Reports the Cause of Death: Python 2 syntax, outdated imports, broken `requirements.txt`.
2. **Ritual.** Applies rule-based fixes and produces a Resurrection Diff and a generated Dockerfile (text only, never built).
3. **Proof of Life.** Runs the revived project in a subprocess inside a temp venv with a timeout and streams the logs.

There are no LLM calls, and the engine makes no network calls. Only `prove` runs the repaired project, in a temporary virtualenv that installs from a local wheelhouse with `pip --no-index` (no network). Dependency fixes come from built-in mapping tables.

## Status

Stage 1 (backend engine, CLI and two broken sample repositories) is complete and tested. The dashboard and `serve` command (Stage 2) are implemented (see [docs/STAGE2.md](docs/STAGE2.md)). The opt-in Node.js `package.json` modernizer (Stage 4, `--node`) is implemented (see [docs/STAGE4.md](docs/STAGE4.md)). See [docs/STAGE1.md](docs/STAGE1.md) for components, limitations and exact commands, and [docs/STAGE1_EVIDENCE.md](docs/STAGE1_EVIDENCE.md) for captured run output.

## Scope

- v1: Python repos (Python 2 to 3 syntax, outdated imports, broken `requirements.txt`). Requires Python 3.11.
- Stretch (implemented, opt-in with `--node`): Node.js `package.json` manifest modernization. JavaScript sources are never rewritten.
- The hosted demo runs only the bundled `samples/`. Uploaded-repo mode is local only.

## License

MIT. See [LICENSE](LICENSE).

## Setup

Grimoire requires Python 3.11. The engine parses Python 2 code with the standard library's `lib2to3`, which is removed in Python 3.13 and deprecated in 3.12.

```
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'        # needs network once, for pytest and hypothesis
python -m pytest -q            # backend tests
node --test tests/frontend/    # frontend tests (needs Node.js)
```

`pip install -e .` alone installs Grimoire with no dependencies. Run the commands below from the repository root so the relative paths (`samples/`, `wheelhouse`) resolve.

Quick check that reaches ALIVE on both samples:

```
python -m grimoire prove samples/sample-legacy-1
python -m grimoire prove samples/sample-legacy-2 --wheelhouse wheelhouse
```

Without `--wheelhouse`, sample 2 reports `UNVERIFIED` (exit 2) because its dependencies cannot be installed offline.

## Demo script (dead, then revived)

Every command and click below was run during Stage 5. Run from the repository root with the venv from Setup active.

Terminal, sample 1 (Tally Keeper):

```
python samples/sample-legacy-1/main.py          # SyntaxError at line 39 (0755), exit 1: the project is dead
python -m grimoire autopsy samples/sample-legacy-1   # Cause of Death: SYNTAX: 10 findings
python -m grimoire prove samples/sample-legacy-1     # PROOF: ALIVE, prints TALLY KEEPER ALIVE, exit 0
python -m grimoire prove samples/sample-legacy-2 --wheelhouse wheelhouse   # ALIVE, exit 0 (LOST LEDGER ALIVE)
```

The CLI and dashboard have no "before" proof label, so the demo does not show a status changing from one label to another. What it shows: the autopsy lists 10 findings (9 for sample 2) and after repair the findings count is zero. The original `main.py` fails with a `SyntaxError`, and the revived one runs and prints its `ALIVE` line (`TALLY KEEPER ALIVE`), with proof status `ALIVE`. `STILL_DEAD` is reported only when the repaired project fails to run; this demo never produced that status.

Dashboard:

1. `python -m grimoire serve`, then open http://127.0.0.1:8765/ (hosted mode).
2. Click the `sample-legacy-1` card.
3. Click **Scan repository**. The Autopsy panel lists 10 findings.
4. Leave **Include proof run** checked (it is by default) and click **Resurrect**.
5. The outcome reads "Resurrected (SUCCESS)". Open the **Diff**, **Dockerfile**, **Validation** and **Proof log** tabs. The proof log shows `Status: ALIVE, exit code 0` and `TALLY KEEPER ALIVE`.
6. Repeat with `sample-legacy-2` (9 findings, patches `main.py` and `requirements.txt`, proof ALIVE using the bundled wheelhouse).
7. Node: select `sample-legacy-3`, tick **Node support**, Scan repository (7 findings instead of 2 INFO), Resurrect. `package.json` is repaired and the diff shows it. The outcome is PARTIAL: proof is UNVERIFIED ("no entry point found; nothing was run") because Grimoire never runs Node or npm. `EMBER LEDGER ALIVE` is not proven.

## How Kiro was used

- **Specs** (`.kiro/specs/grimoire-core/`): `requirements.md`, `design.md` and `tasks.md`. The work was done task by task from `tasks.md` (tasks 1 to 30), and tests follow the task list. Later requirement changes (for example Req 5.6 and 5.7 for the Node Dockerfile) were written into the spec before the code.
- **Steering** (`.kiro/steering/`): `product.md` (what Grimoire is and its constraints), `tech.md` (Python 3.11, stdlib only, `lib2to3`), `structure.md` (repository layout) and `quality.md` (test and property rules: idempotent, parses, deterministic, non-destructive).
- **Hooks** (`.kiro/hooks/pytest-on-save.json`): a `PostFileSave` hook with matcher `(src|tests)[/\\].*\.py$` that runs `python -m pytest -q -x`. The file exists and tests check its contents and matcher. The user observed it in the Kiro IDE (2026-11-28, version unknown): saving `src/grimoire/models.py` triggered pytest and saving `samples/sample-legacy-1/main.py` did not, so spec task 27 is ticked. This is the user's report, not something the agent observed. See [docs/STAGE5.md](docs/STAGE5.md).

## Dashboard (Stage 2)

```
python -m grimoire serve                 # http://127.0.0.1:8765/ (hosted mode: only the bundled samples/)
python -m grimoire serve --mode local    # local mode: also scan a local path or upload a zip
```

Open the URL, pick a sample, press Scan, then Resurrect. See [docs/STAGE2.md](docs/STAGE2.md) for screens, the API and limitations, and [docs/STAGE2_EVIDENCE.md](docs/STAGE2_EVIDENCE.md) for captured output.

## CLI (Stage 1)

```
python -m grimoire autopsy PATH [--node] [--json]
python -m grimoire revive PATH [--node] [--output DIR] [--json]
python -m grimoire prove PATH [--node] [--output DIR] [--wheelhouse DIR] [--timeout SECONDS] [--json]
```

`revive` repairs an isolated temporary copy and never modifies PATH. With `--output DIR` (a new or empty directory outside PATH) the revived copy is written there, with originals of changed files under `.grimoire-backup/` and a generated `Dockerfile.grimoire`. `prove` also runs the entry point in a temporary virtual environment, installing dependencies only from a local `--wheelhouse` (`pip --no-index`). Dependencies that cannot be installed offline give `UNVERIFIED`.

`--node` also analyzes and repairs `package.json` manifests from an offline table (no npm, no network). Without it a `package.json` is reported as `UNSUPPORTED_MANIFEST` and not checked.

Exit codes: 0 ALIVE (or no remaining findings), 1 STILL_DEAD or TIMED_OUT, 2 UNVERIFIED, 3 internal or usage error.

`serve` starts the dashboard (see above). It uses the bundled `wheelhouse/` for proof runs.
