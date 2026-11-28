# Stage 4: Node.js manifest modernizer (spec task 29, Req 10)

Stage 4 adds the stretch feature: `package.json` analysis and repair. It is **opt-in**, so every Stage 1-3 behavior is unchanged unless Node support is enabled.

```
python -m grimoire autopsy PATH --node
python -m grimoire revive  PATH --node [--output DIR]
python -m grimoire prove   PATH --node
```

From Python: `autopsy.autopsy(path, node=True)` and `revive.revive(path, node=True)`.

## What it does

Everything comes from `src/grimoire/data/node_map.json`. No npm command, no registry lookup, no JavaScript source is read or rewritten (Req 10.2, 10.4).

| Rule | Category / severity / class | Effect |
|---|---|---|
| `NODE_RENAMED_PACKAGE` | DEPENDENCY / WARNING / AUTOMATIC | `"jade": "~1.11.0"` becomes `"jade": "npm:pug@^3.0.2"` |
| `NODE_BAD_RANGE` | DEPENDENCY / ERROR / AUTOMATIC | a range that cannot reach a working release is replaced (`lodash ^3.10.1` becomes `^4.17.21`) |
| `NODE_ENGINE_OUTDATED` | MANIFEST / WARNING / AUTOMATIC | `engines.node` that excludes every Node.js from 18 on becomes `>=18` |
| `NODE_DEPRECATED_PACKAGE` | DEPENDENCY / WARNING / MANUAL | reported only (`request`, `tslint`, ...): there is no safe automatic replacement |
| `INVALID_MANIFEST` (existing) | MANIFEST / ERROR / MANUAL | JSON that does not parse, is not an object, or contains `NaN` |

Sections repaired: `dependencies`, `devDependencies`, `optionalDependencies`. `peerDependencies` are reported only.

## Design decisions

- **Opt-in flag, not auto-detect.** Req 10 says "where Node support is enabled", and the existing test `test_unsupported_is_never_a_pass` requires a `package.json` to be `UNSUPPORTED_MANIFEST` by default. With `--node` the manifest is `ANALYZED` in the coverage table; JavaScript files stay `UNSUPPORTED` because nothing analyzes them.
- **Renames use npm aliases, not a plain rename.** Req 10.2 forbids rewriting JS, so a plain rename would leave `require('node-uuid')` pointing at a package that is no longer installed. `"node-uuid": "npm:uuid@^9.0.1"` installs the new package under the old name, so existing `require()` calls keep resolving. The catch: it fixes installability, not API differences between major versions.
- **Targeted text edits, not re-serialization.** `fix_manifest` locates each value's exact span and replaces only that string, so indentation, CRLF, array layout, escapes and key order are byte-identical and the diff shows just the changed lines. Each edit is verified by re-parsing and comparing with the expected data; if that ever fails, it falls back to the JSON encoder with the original indent and line ending.
- **Range handling is conservative.** `upper_bound()` understands `^ ~ x-ranges < <= exact ||`. Anything it does not understand (tags, URLs, `file:`, `workspace:`, `npm:` aliases, hyphen ranges, unbounded `>=`) returns `None`, which always means "do not flag". A range is outdated only when no version it allows reaches the table's `below`.
- **Idempotence is guaranteed by construction.** Aliases (`npm:`) are skipped on re-run, and a test asserts that no table replacement matches its own rule.
- **Same shape as the Python side.** `fix_manifest(text, file) -> (text, findings)` mirrors `requirements.fix_requirements`; autopsy discards the text and `revive` writes it. `revive(node=True)` also adds a validation row "all package.json files parse".

## Files

`src/grimoire/nodejs.py`, `src/grimoire/data/node_map.json` (new); `models.py` (4 rules), `autopsy.py`, `revive.py`, `cli.py`, `dashboard/results.py` (action text per rule); fixture `tests/fixtures/node-legacy/`; tests `tests/unit/test_nodejs.py` (88), `tests/property/test_nodejs_properties.py` and `tests/property/nodejs_checks.py`.

## Verification

Run on Python 3.11 in a fresh venv with `pip install -e '.[dev]'` (pytest 9.2.0, Hypothesis 6.170.23):

- `python -m pytest -q`: 299 passed, 0 failed (88 new unit tests in `tests/unit/test_nodejs.py` plus the Hypothesis test `tests/property/test_nodejs_properties.py`, on top of the 210 Stage 1-3 tests).
- `node --test tests/frontend/`: 19 passed.
- The property checks in `nodejs_checks.py` (valid JSON, key order kept at every level, idempotent, deterministic, only dependency sections and `engines.node` touched, clean manifests returned byte for byte) also held on 20,000 random manifests with a plain random loop (seed 1234) before the Hypothesis run.
- Fixture run: `revive tests/fixtures/node-legacy --node` produced a diff of 12 changed lines (6 removed, 6 added) in `package.json` only; `index.js` and the source tree stayed byte-identical.

## Known limitations

- `node_map.json` replacement ranges (`pug ^3.0.2`, `uuid ^9.0.1`, `coffeescript ^2.7.0`, `lodash ^4.17.21`, `fsevents ^2.3.2`) and the deprecation list are from maintainer knowledge, not checked against the registry, because the engine cannot go online. The table is small on purpose; extend it with the same shape.
- The `engines.node` floor of 18 is a table value (`engines_node.below`). Node 18 is itself end-of-life, so raise it if you want a stricter floor.
- A pure Node project still gets `UNVERIFIED` proof ("no entry point found"). With Node support on it now gets a Node Dockerfile (see Stage 5); `npm`-based proof is out of scope (no npm, Req 10.4).
- A remaining `NODE_DEPRECATED_PACKAGE` warning counts as an unresolved finding, so in a mixed Python + Node repo proof reports `STILL_DEAD` without running the project (same rule as `UNKNOWN_IMPORT`).
- Stage 5 added the dashboard "Node support" toggle and `samples/sample-legacy-3` (see [STAGE5.md](STAGE5.md)).
- Spec task 27 (pytest-on-save hook) still needs the Kiro IDE to observe.
