# Grimoire: Quality

## Testing
- `pytest` for unit and integration tests. `hypothesis` for properties.
- Required properties for every codemod and for the pipeline:
  1. **Idempotent:** `revive(revive(x)) == revive(x)`.
  2. **Parses:** the patched output of any Python 2 input from the generator passes `ast.parse`.
  3. **Deterministic:** two runs on the same input give identical reports and diffs.
  4. **Non-destructive:** the source repo is byte-identical after a run.
- Hypothesis settings: `derandomize=True` in CI profile, fixed `max_examples`, no deadline flakiness (`deadline=None` for parser-heavy tests).
- Do not add tests for behavior nobody asked for. Tests follow the tasks in `tasks.md`.

## Done criteria for a task
- Its acceptance criteria are met.
- `pytest -q` passes.
- No network access in the engine (socket-blocking test passes).
- No new dependency without a note in `tech.md`.

## Code style
- Type hints on public functions. Frozen dataclasses for data.
- Small functions, no global mutable state.
- Errors are values in reports (a `Finding` with severity), not uncaught exceptions. A file that fails to parse is reported as `UNPARSEABLE` and left untouched.

## Safety
- Never write outside the temp working copy.
- Reject path traversal and symlinks that escape the repo root.
- Hosted demo mode refuses any path that is not in the bundled sample allowlist.
- Subprocess: no shell, timeout required, minimal env.

## Output quality
- Diffs are standard unified diffs with repo-relative paths.
- Messages in Cause of Death name the file, line, rule ID and a one-line reason.
