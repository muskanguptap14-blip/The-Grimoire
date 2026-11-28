# Stage 2 Checklist

Maps the dashboard capabilities to code and tests. The list of 11 capabilities below is derived from the Stage 2 feature plan (FEAT-003 sections and behavior), because the original numbered request was not available to the implementer.
Spec tasks 25 and 26 are done. Tasks 27 and 28 are deferred to Stage 3. Sample names remain `sample-legacy-1` and `sample-legacy-2`.

Paths: server `src/grimoire/dashboard/server.py`, payloads `src/grimoire/dashboard/results.py`, UI `src/grimoire/dashboard/static/`.

| # | Capability | Code | Tests |
|---|---|---|---|
| 1 | Header with mode badge and health | `index.html` header, `app.js` health check, `GET /api/health` | `tests/dashboard/test_server.py::test_health_and_headers` |
| 2 | Repository panel: bundled samples, local path, zip upload, hosted explanation | `app.js` sample list, `GET /api/samples`, `POST /api/upload`, `resolve_source`, `safe_extract` | `test_samples_listing_is_data_driven`, `test_hosted_rejects_path_and_upload_and_unknown`, `test_local_path_accepted_and_bad_paths_handled`, `test_upload_*` |
| 3 | Autopsy overview: tiles, severity chart, Cause of Death, coverage | `results.autopsy_payload`, `lib.js` chart helpers | `test_autopsy_matches_engine`, `tests/dashboard/test_results.py`, `tests/frontend/lib.test.js` |
| 4 | Findings table with filter, search and sort | `app.js`, `lib.js` `filterFindings`, `sortFindings` | `tests/frontend/lib.test.js` |
| 5 | Recovery plan grouped by rule, with pipeline visual | `results.build_plan`, `RULE_ACTIONS`, `lib.js` `pipelineNodes` | `test_action_table_covers_every_rule`, `test_plan_groups_by_rule`, `pipelineNodes` tests |
| 6 | Resurrect with include-proof option and caution | `POST /api/runs`, `Server.start_run` | `test_run_reaches_success_equal_to_direct_revive`, `test_run_without_prove_is_partial_and_has_no_prove_stage` |
| 7 | Live progress: stage timeline and SSE log, with polling fallback | `Run.emit`, `_stream`, `app.js` EventSource and polling | `test_sse_order_replay_and_live_proof_lines`, `eventLogLine` test |
| 8 | Results: outcome banner, stats, before and after, patched files | `results.classify_outcome`, `results.stats`, `result_payload` | `tests/dashboard/test_results.py`, `tests/dashboard/test_e2e_samples.py` |
| 9 | Repair detail: diff, Dockerfile, validation, proof, JSON download | `app.js` tabs and `downloadReport`, `lib.js` diff helpers | `classifyDiffLine`, `parseDiff`, `splitDiffByFile` tests |
| 10 | Error banners with retry, safe error handling | `ApiError`, `send_error`, `_dispatch`, error banner in `app.js` | `test_content_type_and_body_errors`, `test_host_and_origin_rejected`, `test_too_many_concurrent_runs` |
| 11 | Offline, CSP-clean, accessible static UI and wheelhouse for sample 2 | `static/*`, `wheelhouse/` | `tests/dashboard/test_static.py`, `test_sample2_without_wheelhouse_is_partial`, `test_static_serving_and_traversal` |

Other items: engine hooks (`revive.on_event`, `revive.on_line`, `verify.on_line`) are covered by the existing Stage 1 suites and the SSE test. `serve` exit codes are covered by `tests/integration/test_pipeline.py::test_cli_exit_codes`. `/favicon.ico` returns 204 (`test_e2e_samples.py::test_favicon_is_quiet`).
