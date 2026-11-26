# Grimoire

Grimoire is a deterministic software-archaeology and resurrection engine, built for the Kiroween Resurrection category.

It takes a dead repository and does three things:

1. **Autopsy.** Reports the Cause of Death: Python 2 syntax, outdated imports, broken `requirements.txt`.
2. **Ritual.** Applies rule-based fixes and produces a Resurrection Diff and a generated Dockerfile (text only, never built).
3. **Proof of Life.** Runs the revived project in a subprocess inside a temp venv with a timeout and streams the logs.

There are no LLM calls and no network access at runtime. Dependency fixes come from built-in mapping tables.

## Status

Stage 1 (backend engine, CLI and two broken sample repositories) is complete and tested. The dashboard and `serve` command are Stage 2. See [docs/STAGE1.md](docs/STAGE1.md) for components, limitations and exact commands, and [docs/STAGE1_EVIDENCE.md](docs/STAGE1_EVIDENCE.md) for captured run output.

## Scope

- v1: Python repos (Python 2 to 3 syntax, outdated imports, broken `requirements.txt`). Requires Python 3.11.
- Stretch: Node.js `package.json` manifest modernization.
- The hosted demo runs only the bundled `samples/`. Uploaded-repo mode is local only.

## License

MIT. See [LICENSE](LICENSE).

## CLI (Stage 1)

```
python -m grimoire autopsy PATH [--json]
python -m grimoire revive PATH [--output DIR] [--json]
python -m grimoire prove PATH [--output DIR] [--wheelhouse DIR] [--timeout SECONDS] [--json]
```

`revive` repairs an isolated temporary copy and never modifies PATH. With `--output DIR` (a new or empty directory outside PATH) the revived copy is written there, with originals of changed files under `.grimoire-backup/` and a generated `Dockerfile.grimoire`. `prove` also runs the entry point in a temporary virtual environment, installing dependencies only from a local `--wheelhouse` (`pip --no-index`). Dependencies that cannot be installed offline give `UNVERIFIED`.

Exit codes: 0 ALIVE (or no remaining findings), 1 STILL_DEAD or TIMED_OUT, 2 UNVERIFIED, 3 internal or usage error.

`serve` (the dashboard) is Stage 2 and is not implemented; the command exits with code 3.
