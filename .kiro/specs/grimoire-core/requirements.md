# Requirements: Grimoire Core

## Introduction
Grimoire diagnoses a dead repository, revives it with deterministic rules, and proves it runs. Terms: **Repo** is the input project. **Working Copy** is a temp copy of the Repo. **Finding** is one diagnosed problem. **Mapping Table** is a built-in JSON data table.

Requirements use EARS patterns: Ubiquitous (The system shall), Event-driven (WHEN), State-driven (WHILE), Unwanted (IF ... THEN), Optional (WHERE).

## Requirement 1: Autopsy
**User story:** As a developer, I want to know why my repo is dead.

1. WHEN the user starts an autopsy on a Repo, THE Grimoire SHALL scan all `.py`, `requirements.txt` files (and `package.json` where Node support is enabled) in sorted order.
2. THE Grimoire SHALL classify each Finding with a rule ID, category (`SYNTAX`, `IMPORT`, `DEPENDENCY`, `MANIFEST`), file, line and one-line reason.
3. WHEN a `.py` file fails `ast.parse`, THE Grimoire SHALL attempt to parse it with the Python 2 grammar and, IF that succeeds, record it as Python 2.
4. IF a file parses under neither grammar, THEN THE Grimoire SHALL record an `UNPARSEABLE` Finding and leave the file unmodified.
5. THE Grimoire SHALL produce a Cause of Death summary that ranks categories by Finding count, with ties broken alphabetically.
6. THE Grimoire SHALL skip `.git`, `venv`, `.venv`, `node_modules` and `__pycache__` directories.

## Requirement 2: Python 2 to 3 syntax codemods
**User story:** As a developer, I want Python 2 syntax converted to valid Python 3.

1. WHEN a Python 2 file contains a `print` statement, THE Grimoire SHALL rewrite it as a `print()` call, including `>>file` redirection and trailing-comma forms.
2. WHEN a file contains `except X, e:`, THE Grimoire SHALL rewrite it as `except X as e:`.
3. WHEN a file contains `raise E, "msg"`, THE Grimoire SHALL rewrite it as `raise E("msg")`.
4. WHEN a file contains backtick repr, `<>`, `exec` statements, `ur""` literals, or old octal literals (`0755`), THE Grimoire SHALL rewrite them to Python 3 equivalents.
5. WHEN a file uses `dict.has_key`, `iteritems`, `itervalues`, `iterkeys`, `xrange`, `raw_input`, `unicode`, `long`, or `basestring`, THE Grimoire SHALL replace them with Python 3 equivalents.
6. THE Grimoire SHALL preserve comments, blank lines and indentation of untouched code.
7. THE Grimoire SHALL ensure every patched file passes `ast.parse`.
8. IF a patched file fails `ast.parse`, THEN THE Grimoire SHALL discard the patch for that file, keep the original, and record a `PATCH_REJECTED` Finding.
9. THE Grimoire SHALL be idempotent: applying it to its own output SHALL produce no further change.

## Requirement 3: Outdated imports
1. WHEN a file imports a module listed in the imports Mapping Table (for example `urllib2`, `ConfigParser`, `Queue`, `StringIO`, `cPickle`, `Tkinter`), THE Grimoire SHALL rewrite the import and the matching attribute uses to the Python 3 module.
2. WHEN `try: import X except ImportError: import Y` fallbacks exist, THE Grimoire SHALL leave them valid and not duplicate them.
3. IF a module has no Mapping Table entry and is not in the Python 3.11 stdlib or the Repo, THEN THE Grimoire SHALL record an `UNKNOWN_IMPORT` Finding without changing the code.
4. THE Grimoire SHALL NOT access the network to resolve imports.

## Requirement 4: Broken requirements.txt
1. WHEN `requirements.txt` names a package in the packages Mapping Table as renamed (for example `PIL` to `Pillow`, `BeautifulSoup` to `beautifulsoup4`), THE Grimoire SHALL replace the name.
2. WHEN a requirement uses a pin known to be unsatisfiable on Python 3.11 per the Mapping Table, THE Grimoire SHALL replace it with the table's compatible specifier.
3. WHEN a line is malformed, a duplicate, or a removed package (for example `distribute`), THE Grimoire SHALL fix or drop it and record a Finding.
4. THE Grimoire SHALL keep comments, `-r` includes and option lines unchanged.
5. THE Grimoire SHALL write requirements in a stable order that preserves the original order for kept lines.
6. THE Grimoire SHALL be idempotent on `requirements.txt`.

## Requirement 5: Resurrection Diff and Dockerfile
1. THE Grimoire SHALL produce a unified diff of every changed file, with repo-relative paths, sorted by path.
2. THE Grimoire SHALL NOT modify the original Repo.
3. WHEN revival completes, THE Grimoire SHALL generate a Dockerfile as text based on `python:3.11-slim`, installing `requirements.txt` and using the detected entry point.
4. THE Grimoire SHALL NOT build or run the Dockerfile.
5. IF a Dockerfile already exists, THEN THE Grimoire SHALL write the generated one as `Dockerfile.grimoire` in the Working Copy.
6. WHERE Node support is enabled and the Working Copy is Node-only (a root `package.json` and no Python source files), THE Grimoire SHALL instead generate a Dockerfile as text based on `node:22-slim`, with exactly these lines in order: `FROM node:22-slim`, `WORKDIR /app`, `COPY package*.json ./`, `RUN npm install --omit=dev`, `COPY . .` and `CMD ["node", "<main>"]`, where `<main>` is the `main` field of `package.json`, or `index.js` when it is missing or unsafe. Requirement 5.3 applies to every other project, with byte-identical output.
7. THE Grimoire SHALL NOT build or run the Node Dockerfile, and SHALL NOT invoke `npm` or `docker` (Req 5.4, Req 10.4).

## Requirement 6: Proof of Life
1. WHEN verification starts, THE Grimoire SHALL create a venv in a temp directory and run the entry point in a subprocess without a shell.
2. THE Grimoire SHALL enforce a timeout (default 20 seconds, configurable) and terminate the process group on expiry.
3. WHILE the subprocess runs, THE Grimoire SHALL stream stdout and stderr lines to the log in order, capped at 1 MiB.
4. THE Grimoire SHALL report `ALIVE` (exit code 0), `STILL_DEAD` (non-zero exit), `TIMED_OUT`, or `UNVERIFIED` (dependencies not available offline).
5. THE Grimoire SHALL install dependencies only from a local wheelhouse, with no index access.
6. THE Grimoire SHALL delete the temp directories after the run, including on error.
7. THE Grimoire SHALL pass a minimal environment (no inherited secrets).

## Requirement 7: Determinism and offline operation
1. THE Grimoire SHALL NOT call any LLM or make any network request at runtime.
2. THE Grimoire SHALL produce byte-identical reports and diffs for identical inputs.
3. THE Grimoire SHALL source all dependency and import fixes from Mapping Tables in `src/grimoire/data/`.

## Requirement 8: Dashboard
1. THE Dashboard SHALL use a dark theme and show three panels: Cause of Death, Resurrection Diff, Live Proof-of-Life.
2. WHEN the user selects a sample, THE Dashboard SHALL run autopsy, revive and prove, then fill the panels.
3. WHILE verification runs, THE Dashboard SHALL stream log lines to the Live Proof-of-Life panel.
4. THE Dashboard SHALL load no external assets.
5. WHERE the server runs in hosted mode, THE Dashboard SHALL offer only the bundled samples and the server SHALL reject any other path with HTTP 403.
6. WHERE the server runs in local mode, THE Dashboard SHALL accept a local repo path.
7. IF a run fails, THEN THE Dashboard SHALL show the error in the log panel and stay usable.

## Requirement 9: Samples
1. THE Grimoire SHALL include two ORIGINAL mini-repos in `samples/`, written from scratch.
2. Each sample SHALL fail to run before revival and print a success line after revival under Python 3.11.
3. Between them, the samples SHALL exercise print statements, `except X, e`, old imports, and a broken `requirements.txt`.
4. Samples SHALL run with the standard library only, so Proof of Life works offline.

## Requirement 10 (stretch): Node.js manifest modernization
1. WHERE Node support is enabled and a `package.json` exists, THE Grimoire SHALL replace deprecated packages and outdated version ranges using `node_map.json`.
2. THE Grimoire SHALL NOT rewrite JavaScript source files.
3. THE Grimoire SHALL preserve key order in `package.json` and be idempotent.
4. THE Grimoire SHALL NOT run `npm` or access the registry.
