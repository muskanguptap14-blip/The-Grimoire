# Tasks: Grimoire Core

Ordered smallest first. Each task is done when its acceptance criteria hold and `pytest -q` passes. `[PBT]` marks property-based tests (Hypothesis). Requirement numbers refer to `requirements.md`.

- [x] 1. Project skeleton
  - Create `pyproject.toml` (Python >=3.11,<3.13, dev extras: pytest, hypothesis), `src/grimoire/__init__.py`, `tests/conftest.py`, `.gitignore`.
  - Acceptance: `pip install -e ".[dev]"` works; `pytest -q` runs (zero tests is fine); `python -c "import grimoire"` succeeds.

- [x] 2. Data models
  - Implement `models.py` (Finding, FilePatch, ProofResult, Report) as frozen dataclasses.
  - Acceptance: models are immutable and hashable; a unit test covers construction and `dataclasses.replace`. (Req 1.2)

- [x] 3. Hypothesis profiles
  - Register `ci` (derandomize, fixed max_examples, `deadline=None`) and `dev` profiles in `conftest.py`.
  - Acceptance: `pytest --hypothesis-profile=ci` runs a trivial property; results are repeatable. (quality.md)

- [x] 4. Repo scanner
  - `scan.py`: list `.py`, `requirements.txt`, `package.json`, sorted, skipping ignored directories, repo-relative `/` paths, rejecting symlinks that escape the root.
  - Acceptance: unit tests on a temp tree show correct, sorted output and exclusions. (Req 1.1, 1.6)

- [x] 5. Python 2 parser facade
  - `py2parse.py`: `classify(source) -> PY3 | PY2 | UNPARSEABLE`, `parse_py2(source) -> CST`, `render(tree) -> str`.
  - Acceptance: `print "x"` classifies as PY2; valid Python 3 as PY3; garbage as UNPARSEABLE.
  - [PBT] For Python 2 snippets generated from the construct strategy, `render(parse_py2(s)) == s` (lossless round-trip). (Req 1.3, 2.6)

- [x] 6. Construct strategies
  - `tests/property/strategies.py`: Hypothesis strategies that generate valid Python 2 statements (print forms, except forms, raise forms, builtins, dict methods, octals, backticks) and small multi-statement modules.
  - Acceptance: every generated sample parses with `parse_py2`; none parse with `ast.parse` when the construct is Py2-only.

- [x] 7. Codemod: `print_stmt`
  - Acceptance: handles `print`, `print x, y`, `print "a" % b`, `print >>sys.stderr, x`, trailing comma, and bare `print`. Existing `print(...)` calls are untouched. (Req 2.1)
  - [PBT] Output parses with `ast.parse`; applying the rule twice equals applying it once.

- [x] 8. Codemod: `except_as`
  - Acceptance: `except X, e:` and `except (A, B), e:` become `as` forms. (Req 2.2)
  - [PBT] Output parses; idempotent.

- [x] 9. Codemod: `raise_stmt`
  - Acceptance: `raise E, "m"` becomes `raise E("m")`; `raise E` and `raise` unchanged. (Req 2.3)
  - [PBT] Output parses; idempotent.

- [x] 10. Codemods: `backticks`, `ne_operator`, `exec_stmt`, `octal_literals`, `string_prefix`
  - Acceptance: each construct converts per Req 2.4, one test per construct, with comments and whitespace preserved.
  - [PBT] Output parses; idempotent for each rule.

- [x] 11. Codemods: `builtins` and `dict_methods`
  - Acceptance: `xrange`, `raw_input`, `unicode`, `long`, `basestring`, `has_key`, `iteritems`, `itervalues`, `iterkeys` converted (Req 2.5). Names that are shadowed locally or used as attributes of other objects (for example `obj.xrange`) are untouched.
  - [PBT] Output parses; idempotent.

- [x] 12. Codemod pipeline and reject path
  - `codemods/__init__.py` registers rules in the fixed order; `apply_all(source)` returns a `FilePatch` or a `PATCH_REJECTED` Finding when `ast.parse` fails on output.
  - Acceptance: a forced-bad rule (test double) results in the original being kept. (Req 2.7, 2.8)
  - [PBT] **Patched output parses:** for generated multi-statement Python 2 modules, `ast.parse(apply_all(m).after)` succeeds.
  - [PBT] **Idempotent:** `apply_all(apply_all(m).after).after == apply_all(m).after`.
  - [PBT] **Deterministic:** two runs give equal results.

- [x] 13. Imports mapping table and validator
  - `data/imports_map.json` (urllib2, urlparse, ConfigParser, Queue, StringIO, cStringIO, cPickle, Tkinter, httplib, HTMLParser, `__builtin__`, and similar), plus a test that validates the table shape.
  - Acceptance: no duplicate keys; every target is a non-empty string and, when listed as stdlib, exists in `sys.stdlib_module_names`. (Req 3.1, 7.3)

- [x] 14. Imports rewriter
  - `imports.py`: rewrite `import X`, `import X as Y`, `from X import a`, and attribute uses; leave `try/except ImportError` fallbacks valid; emit `UNKNOWN_IMPORT` for unmapped non-stdlib, non-repo modules.
  - Acceptance: unit tests for each form. (Req 3.1 to 3.3)
  - [PBT] Output parses; idempotent; no old module names remain for mapped modules.

- [x] 15. Requirements parser
  - `requirements.py`: parse into lines keeping comments, blank lines, options and `-r`; normalize names per PEP 503.
  - Acceptance: parse then render returns the input unchanged.
  - [PBT] `render(parse(text)) == text` for generated requirements files. (Req 4.4)

- [x] 16. Packages mapping table and requirements fixer
  - `data/packages_map.json` (`renames`, `removed`, `bad_pins`); `fix_requirements(text) -> (text, findings)`.
  - Acceptance: `PIL` becomes `Pillow`, `distribute` is dropped, duplicates removed, malformed lines flagged, order of kept lines preserved. (Req 4.1 to 4.3, 4.5)
  - [PBT] Idempotent; kept lines keep relative order; no removed package names in output.

- [x] 17. Autopsy and Cause of Death
  - `autopsy.py`: run scanner, classify, collect Findings (no patching), and produce a ranked Cause of Death summary.
  - Acceptance: category counts are correct; ties are broken alphabetically; unparseable files are flagged. (Req 1.2 to 1.5)
  - [PBT] Findings order and summary are the same for any shuffling of the scan input order.

- [x] 18. Samples (original)
  - Write `samples/sample-legacy-1/` and `samples/sample-legacy-2/` (user override of the original names crypt_calculator and lost_ledger) from scratch per `design.md`, each with a short README line saying it is an original sample.
  - Acceptance: under Python 3.11 each fails to run before revival; each has at least the constructs listed in Req 9.3 between them; stdlib only. (Req 9)

- [x] 19. Revive and Resurrection Diff
  - `diffing.py` and `revive(repo) -> Report`: copy repo to a temp Working Copy, run codemods, imports and requirements, build the unified diff.
  - Acceptance: both samples produce a non-empty sorted diff; original sample files are byte-identical afterwards. (Req 5.1, 5.2)
  - [PBT] Source tree hash before and after `revive` is equal.

- [x] 20. Dockerfile generator
  - `dockerfile.py` with entry detection and `Dockerfile.grimoire` fallback.
  - Acceptance: golden-file tests for both samples; nothing runs Docker. (Req 5.3 to 5.5)

- [x] 21. Verifier
  - `verify.py` per `design.md`: temp venv, offline install from wheelhouse, subprocess with timeout, process-group kill, output cap, minimal env, cleanup.
  - Acceptance: a test script that prints and exits 0 gives ALIVE; exit 1 gives STILL_DEAD; a sleeping script gives TIMED_OUT within the timeout plus a margin; missing package gives UNVERIFIED; temp dirs are gone afterwards. (Req 6)

- [x] 22. Offline guarantee test
  - Test blocks `socket.socket` and runs the full pipeline on both samples.
  - Acceptance: pipeline succeeds with sockets blocked; a grep test asserts the engine has no imports of `requests`, `urllib.request`, `http.client`, or `socket`. (Req 7.1)

- [x] 23. CLI
  - `cli.py` and `__main__.py`: `autopsy`, `revive`, `prove`, `serve`, with the exit codes in `design.md`.
  - Acceptance: `python -m grimoire revive samples/sample-legacy-1` prints the diff and exits 0 after proving ALIVE.

- [x] 24. End-to-end sample test
  - Acceptance: for each sample, proof is `STILL_DEAD` on the original and `ALIVE` after revival. Running revive twice gives identical reports. (Req 9.2, 7.2)
  - [PBT] Report equality across repeated runs for generated small repos (one `.py` plus one `requirements.txt`).

- [ ] 25. Dashboard server
  - `dashboard/server.py` with routes, hosted and local modes, SSE log stream, CSP header.
  - Acceptance: in hosted mode, `{path: "/etc"}` gets 403 and unknown sample IDs get 404; local mode accepts a path; SSE delivers lines in order. (Req 8.3, 8.5, 8.6)

- [ ] 26. Dashboard UI
  - `static/index.html`, `app.css`, `app.js`: dark theme, three panels, sample picker, diff coloring, log streaming, error display, `textContent` only.
  - Acceptance: page loads with no external requests (a test greps for `http://`/`https://` in static files); a manual run on both samples fills all three panels. (Req 8.1, 8.2, 8.4, 8.7)

- [ ] 27. Pytest-on-save hook (file already created)
  - `.kiro/hooks/pytest-on-save.json` (trigger `PostFileSave`, matcher `(src|tests)[/\\].*\.py$`, command `python -m pytest -q -x`) and `pytest.ini` (`testpaths = tests`, `norecursedirs = samples`) exist as plain files, so samples are never collected as tests.
  - Acceptance: saving a Python file in `src/` or `tests/` triggers pytest; a failing test shows in the hook output; saving a file in `samples/` does not.

- [ ] 28. README and demo script
  - Document install, CLI, hosted vs local mode, and the Python 3.11 / lib2to3 constraint.
  - Acceptance: following the README from a clean checkout reaches an ALIVE result on a sample.

- [ ] 29. (Stretch) Node manifest modernizer
  - `nodejs.py` and `data/node_map.json`; a small `package.json` sample fixture under `tests/fixtures/`.
  - Acceptance: deprecated packages replaced, key order preserved, no JS files touched, no npm calls. (Req 10)
  - [PBT] Idempotent; output is valid JSON; key order of untouched keys preserved.
