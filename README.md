# Grimoire

Grimoire is a deterministic software-archaeology and resurrection engine, built for the Kiroween Resurrection category.

It takes a dead repository and does three things:

1. **Autopsy.** Reports the Cause of Death: Python 2 syntax, outdated imports, broken `requirements.txt`.
2. **Ritual.** Applies rule-based fixes and produces a Resurrection Diff and a generated Dockerfile (text only, never built).
3. **Proof of Life.** Runs the revived project in a subprocess inside a temp venv with a timeout and streams the logs.

There are no LLM calls, and the engine makes no network calls. Only `prove` runs the repaired project, in a temporary virtualenv that installs from a local wheelhouse with `pip --no-index` (no network). Dependency fixes come from built-in mapping tables.

## Status

Stage 1 (backend engine, CLI and two broken sample repositories) is complete and tested. The dashboard and `serve` command (Stage 2) are implemented (see [docs/STAGE2.md](docs/STAGE2.md)). See [docs/STAGE1.md](docs/STAGE1.md) for components, limitations and exact commands, and [docs/STAGE1_EVIDENCE.md](docs/STAGE1_EVIDENCE.md) for captured run output.

## Scope

- v1: Python repos (Python 2 to 3 syntax, outdated imports, broken `requirements.txt`). Requires Python 3.11.
- Stretch: Node.js `package.json` manifest modernization.
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

## Dashboard (Stage 2)

```
python -m grimoire serve                 # http://127.0.0.1:8765/ (hosted mode: only the bundled samples/)
python -m grimoire serve --mode local    # local mode: also scan a local path or upload a zip
```

Open the URL, pick a sample, press Scan, then Resurrect. See [docs/STAGE2.md](docs/STAGE2.md) for screens, the API and limitations, and [docs/STAGE2_EVIDENCE.md](docs/STAGE2_EVIDENCE.md) for captured output.

## CLI (Stage 1)

```
python -m grimoire autopsy PATH [--json]
python -m grimoire revive PATH [--output DIR] [--json]
python -m grimoire prove PATH [--output DIR] [--wheelhouse DIR] [--timeout SECONDS] [--json]
```

`revive` repairs an isolated temporary copy and never modifies PATH. With `--output DIR` (a new or empty directory outside PATH) the revived copy is written there, with originals of changed files under `.grimoire-backup/` and a generated `Dockerfile.grimoire`. `prove` also runs the entry point in a temporary virtual environment, installing dependencies only from a local `--wheelhouse` (`pip --no-index`). Dependencies that cannot be installed offline give `UNVERIFIED`.

Exit codes: 0 ALIVE (or no remaining findings), 1 STILL_DEAD or TIMED_OUT, 2 UNVERIFIED, 3 internal or usage error.

`serve` starts the dashboard (see above). It uses the bundled `wheelhouse/` for proof runs.
