# Grimoire: Product

Grimoire is a deterministic software-archaeology and resurrection engine. It takes a dead repository, diagnoses why it no longer runs, applies rule-based fixes, and proves the result runs. Built for the Kiroween **Resurrection** category.

## The three stages
1. **Autopsy**: scan the repo and report a *Cause of Death* (Python 2 syntax, removed or renamed stdlib modules, dead or renamed PyPI packages, unpinnable requirements).
2. **Ritual**: apply codemods and manifest fixes. Produce a *Resurrection Diff* (unified diff per file) and a generated Dockerfile.
3. **Proof of Life**: run the revived project in a subprocess inside a temp venv with a timeout. Stream the logs as *Live Proof-of-Life*.

## Hard rules
- **Deterministic and rule-based.** No LLM calls. No network access at runtime. Same input gives byte-identical output.
- Dependency fixes come only from the built-in mapping tables in `src/grimoire/data/`.
- Never modify the user's original repo. Work on a copy in a temp directory.
- The Dockerfile is generated as text. Grimoire never builds or runs Docker.

## Scope
**v1 (must have):** Python repos. Python 2 to 3 syntax, outdated imports, broken `requirements.txt`.
**Stretch:** Node.js `package.json` manifest modernization only (no JS source rewriting).
**Out of scope:** LLM suggestions, auto-fixing logic bugs, building containers, other languages.

## Modes
- **Hosted demo:** runs only the bundled `samples/`. No upload endpoint exists in this mode.
- **Local mode:** accepts any repo path (CLI or dashboard). Local only.

## Dashboard
Dark-themed web UI with three panels: Cause of Death, Resurrection Diff, Live Proof-of-Life logs. It is served by a local server and loads no external assets (no CDN, no web fonts).

## Samples
`samples/` holds two ORIGINAL dead mini-repos written from scratch for this project. Do not copy code from real projects.
