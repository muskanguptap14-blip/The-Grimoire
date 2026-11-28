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
