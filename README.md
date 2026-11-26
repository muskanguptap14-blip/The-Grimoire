# Grimoire

Grimoire is a deterministic software-archaeology and resurrection engine, built for the Kiroween Resurrection category.

It takes a dead repository and does three things:

1. **Autopsy.** Reports the Cause of Death: Python 2 syntax, outdated imports, broken `requirements.txt`.
2. **Ritual.** Applies rule-based fixes and produces a Resurrection Diff and a generated Dockerfile (text only, never built).
3. **Proof of Life.** Runs the revived project in a subprocess inside a temp venv with a timeout and streams the logs.

There are no LLM calls and no network access at runtime. Dependency fixes come from built-in mapping tables.

## Status

Foundation only. The steering files and the `grimoire-core` spec (requirements, design, tasks) are in `.kiro/`. No application code exists yet.

## Scope

- v1: Python repos (Python 2 to 3 syntax, outdated imports, broken `requirements.txt`). Requires Python 3.11.
- Stretch: Node.js `package.json` manifest modernization.
- The hosted demo runs only the bundled `samples/`. Uploaded-repo mode is local only.

## License

MIT. See [LICENSE](LICENSE).
