"""Stage 2 end to end: the HTTP API agrees with the engine for both bundled samples."""

import json

from grimoire import autopsy, revive

from tests.dashboard.test_server import WHEELHOUSE, hosted  # noqa: F401  (fixture)
from tests.integration.test_samples import NAMES, SAMPLES, SUCCESS, tree_hash

import pytest


def test_favicon_is_quiet(hosted):  # noqa: F811
    resp, body = hosted.request("GET", "/favicon.ico")
    assert resp.status == 204 and body == b""


@pytest.mark.parametrize("name", NAMES)
def test_api_matches_engine(hosted, name):  # noqa: F811
    before_tree = tree_hash(SAMPLES / name)

    # scan: findings counts equal the direct autopsy
    direct_scan = autopsy.autopsy(SAMPLES / name)
    status, scan = hosted.json("POST", "/api/autopsy", {"sample": name})
    assert status == 200
    assert scan["summary"]["counts"]["total"] == len(direct_scan.findings)
    assert len(scan["findings"]) == len(direct_scan.findings)

    # run: before/after findings, patched files and proof status equal the direct revive
    direct = revive.revive(SAMPLES / name, prove=True, wheelhouse=WHEELHOUSE)
    _s, started = hosted.json("POST", "/api/runs", {"sample": name})
    snap = hosted.wait_run(started["run_id"])
    result = json.loads(json.dumps(snap["result"]))
    assert snap["state"] == "done" and result["outcome"] == "SUCCESS"
    assert len(result["before"]["findings"]) == len(direct.before_findings)
    assert len(result["after"]["findings"]) == len(direct.findings)
    assert sorted(p["path"] for p in result["patches"]) == sorted(p.path for p in direct.patches)
    assert result["proof"]["status"] == direct.proof.status == "ALIVE"
    assert SUCCESS[name] in result["proof"]["log_lines"]
    assert result["diff"] == direct.diff

    # the source sample is never modified
    assert tree_hash(SAMPLES / name) == before_tree
