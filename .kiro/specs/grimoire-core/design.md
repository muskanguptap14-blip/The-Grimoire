# Design: Grimoire Core

## Pipeline
```
repo path -> scan -> autopsy (Findings) -> revive (patches in Working Copy)
          -> diff + Dockerfile text -> verify (temp venv, subprocess) -> Report
CLI and Dashboard are thin shells over this pipeline.
```
Each stage is a pure function over data models, except `scan` (reads files) and `verify` (spawns a process).

## Data models (`models.py`, frozen dataclasses)
- `Finding(rule_id, category, file, line, reason, severity)`
- `FilePatch(path, before, after, rules_applied)`
- `Report(findings, cause_of_death, patches, diff, dockerfile, proof)`
- `ProofResult(status, exit_code, log_lines, duration_note)`. Status is one of `ALIVE | STILL_DEAD | TIMED_OUT | UNVERIFIED`. Wall-clock duration is shown in the UI only and excluded from the deterministic report.

## How Python 2 files are parsed
Python 3's `ast.parse` raises `SyntaxError` on `print "x"`, `except E, e:`, backticks, `<>`, `exec "code"` and `0755`. Grimoire therefore uses a two-grammar strategy (`py2parse.py`):

1. **Classify.** Try `ast.parse(source)`. If it succeeds, the file is Python 3 (or compatible) and Python 2 codemods are skipped. Import and requirement rules still run.
2. **Parse as Python 2.** If `ast.parse` fails, parse with `lib2to3.pgen2.driver.Driver` using `lib2to3.pygram.python_grammar` (the Python 2 grammar, with `print` as a statement). This produces a lossless concrete syntax tree (CST) that keeps comments, whitespace and prefixes, so unchanged code round-trips byte for byte.
3. **Transform.** Codemods are Grimoire's own visitors over the CST (`codemods/*.py`). Each handles one construct (for example `print_stmt` turns a `print_stmt` node into a `power` node with `print(...)`). Only node types that the rule matches are modified.
4. **Render and validate.** Render the CST with `str(tree)`, then call `ast.parse` on the result. On success, accept the patch. On failure, reject it (Req 2.8): keep the original and add `PATCH_REJECTED`.
5. **Neither parses.** If both grammars fail, record `UNPARSEABLE` and leave the file alone.

**Why lib2to3 and not the `ast` module or `2to3` as a tool:** it is the only stdlib parser that accepts the Python 2 grammar. It is deprecated and removed in Python 3.13, so v1 pins Python 3.11 (see `tech.md`). The dependency is isolated behind `py2parse.py` so it can later be replaced by a vendored copy of the grammar and driver without touching codemods.

**Why own codemods rather than calling `lib2to3.refactor` fixers:** fixers fail on some inputs, have unstable ordering, and give no per-rule reporting. Own visitors give a fixed rule order, a rule ID on every change, and idempotency tests per rule. Where a lib2to3 fixer is simple, the rule may copy its logic with a test.

**Mixed-style files.** Tabs and spaces mix is legal in Python 2 but not Python 3. If a file still fails `ast.parse` after codemods, the whole-file reject path applies.

## Codemod order (fixed)
`print_stmt`, `except_as`, `raise_stmt`, `backticks`, `ne_operator`, `exec_stmt`, `octal_literals`, `string_prefix`, `builtins` (xrange/raw_input/unicode/long/basestring), `dict_methods`, then `imports`. Order matters for idempotency and is covered by a test that re-runs the pipeline.

## Imports (`imports.py`)
Operates on the Python 3 CST/AST after syntax fixes. `imports_map.json` maps `old_module -> {new, attrs}`. Handles `import X`, `import X as Y`, `from X import a`. Attribute uses (`urllib2.urlopen`) are rewritten using the entry's `attrs` sub-map (`urllib2.urlopen` -> `urllib.request.urlopen`). Unknown non-stdlib imports are checked against `sys.stdlib_module_names` and the repo's own modules, otherwise reported as `UNKNOWN_IMPORT`.

## Requirements (`requirements.py`)
Line-based parser that keeps comments and options verbatim. For each requirement line, use `packaging`-free parsing (regex for name, extras, specifiers) to stay dependency-free. `packages_map.json` has: `renames`, `removed`, `bad_pins` (name -> replacement specifier), all offline. Output keeps original order, and dedupes by normalized name (PEP 503) with first occurrence kept.

## Dockerfile (`dockerfile.py`)
Pure string builder: `FROM python:3.11-slim`, `WORKDIR /app`, `COPY requirements.txt` (if present), `RUN pip install --no-cache-dir -r requirements.txt`, `COPY . .`, `CMD ["python", "<entry>"]`. Entry detection order: `__main__.py`, `main.py`, `run.py`, `app.py`, or a `grimoire.toml` `entry` key. Never executed.

## Verification (`verify.py`)
1. Copy patched Working Copy to a temp dir (`tempfile.TemporaryDirectory`).
2. `python -m venv <tmp>/venv` (no pip index use).
3. If requirements exist, `venv/bin/python -m pip install --no-index --find-links <wheelhouse> -r requirements.txt`. If any package is missing from the wheelhouse, status is `UNVERIFIED` and the missing names are logged. Samples use only the stdlib, so they are always verifiable.
4. Run `venv/bin/python <entry>` with `subprocess.Popen([...], shell=False, start_new_session=True, env=minimal, cwd=tmp)`; read lines from a pipe in a thread into a queue.
5. On timeout, `os.killpg`, status `TIMED_OUT`.
6. Cleanup in `finally`.

This is the only place Grimoire runs code from the repo. Hosted mode accepts only allowlisted sample IDs, never paths. Local mode runs whatever the user points it at, which is why it is local only.

## Offline guarantee
No networking modules imported in the engine. A test monkeypatches `socket.socket` to raise and runs the full pipeline on both samples. The `pip install` step uses `--no-index`.

## Dashboard (`dashboard/`)
- `server.py`: stdlib `ThreadingHTTPServer`. Routes: `GET /` (static), `GET /api/samples`, `POST /api/run` (body: `{sample}` or, in local mode, `{path}`), `GET /api/stream/<run_id>` (Server-Sent Events for proof logs).
- Modes: `--mode hosted` (default) allowlists sample IDs and returns 403 for `path`; `--mode local` enables `path`. Binds to `127.0.0.1` in local mode.
- UI: static HTML/CSS/JS, dark theme (CSS variables), three panels. The diff panel colors `+`/`-` lines. The log panel appends SSE lines. No external requests; a strict `Content-Security-Policy: default-src 'self'` header is sent.
- All repo-derived text is inserted with `textContent`, not `innerHTML`, to avoid XSS from hostile repos.

## Samples

> Naming note: the samples are implemented as `samples/sample-legacy-1` (Tally Keeper, replaces crypt_calculator) and `samples/sample-legacy-2` (Lost Ledger, replaces lost_ledger) by user override. Success lines are `TALLY KEEPER ALIVE` and `LOST LEDGER ALIVE`.
- `samples/crypt_calculator/`: Python 2 script with `print` statements, `except ValueError, e`, `raw_input` and `xrange`. Prints `CRYPT CALCULATOR ALIVE` after revival.
- `samples/lost_ledger/`: uses `ConfigParser`, `StringIO`, `urllib2` (for parse helpers only, no network calls made), and a `requirements.txt` with a renamed package and a removed one. Prints `LOST LEDGER ALIVE` after revival; its runtime only needs the stdlib, and requirements fixing is checked by the diff.
Both are written from scratch and kept small.

## Node.js stretch (`nodejs.py`)
Parse `package.json` with `json` (`object_pairs_hook=OrderedDict` equivalent, as dict order is preserved), apply `node_map.json` (renamed or deprecated packages, `engines`), write with 2-space indent and trailing newline. No source rewriting, no npm.

## Error handling
All stage errors become Findings or a failed stage in the Report. The CLI exits 0 for ALIVE, 1 for STILL_DEAD/TIMED_OUT, 2 for UNVERIFIED, 3 for internal errors.

## Testing strategy
- Unit tests for each codemod, the imports rewriter, requirements fixer and Dockerfile generator.
- Hypothesis strategies generate Python 2 snippets from a grammar of constructs (print forms, except forms, raises, builtins) and assert: output parses (`ast.parse`), pipeline is idempotent, and re-running is deterministic.
- Hypothesis strategies for requirements lines assert idempotence and order preservation.
- Integration: both samples go from `STILL_DEAD` before to `ALIVE` after.
- Socket-blocking test for offline guarantee.
