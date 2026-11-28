"""Dashboard server tests: a real server on port 0 in a thread, real pipeline, nothing mocked."""

import http.client
import io
import json
import shutil
import threading
import time
import zipfile
from pathlib import Path

import pytest

from grimoire import autopsy, revive
from grimoire.dashboard import server as srv
from grimoire.dashboard.results import result_payload
from tests.integration.test_samples import NAMES, SAMPLES, tree_hash

ROOT = Path(__file__).resolve().parents[2]
NODE_SAMPLE = "sample-legacy-3"
WHEELHOUSE = ROOT / "wheelhouse"


class Client:
    def __init__(self, server):
        self.port = server.server_address[1]

    def request(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        h = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=data, headers=h)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp, payload

    def json(self, method, path, body=None, headers=None, raw=None):
        resp, payload = self.request(method, path, body, headers, raw)
        return resp.status, json.loads(payload) if payload else None

    def wait_run(self, run_id, timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            _s, snap = self.json("GET", f"/api/runs/{run_id}")
            if snap["state"] in ("done", "error"):
                return snap
            time.sleep(0.1)
        raise AssertionError("run did not finish")


def start(config):
    server = srv.DashboardServer(config)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def hosted():
    server = start(srv.Config(mode="hosted", port=0, wheelhouse=WHEELHOUSE, samples_dir=SAMPLES))
    yield Client(server)
    server.shutdown()
    server.server_close()


@pytest.fixture
def local():
    server = start(srv.Config(mode="local", port=0, wheelhouse=WHEELHOUSE, samples_dir=SAMPLES))
    yield Client(server)
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def samples_untouched():
    before = {n: tree_hash(SAMPLES / n) for n in (*NAMES, NODE_SAMPLE)}
    yield
    assert {n: tree_hash(SAMPLES / n) for n in (*NAMES, NODE_SAMPLE)} == before


def test_health_and_headers(hosted):
    resp, payload = hosted.request("GET", "/api/health")
    body = json.loads(payload)
    assert body["mode"] == "hosted" and body["wheelhouse"]["in_use"] and body["wheelhouse"]["wheels"] >= 4
    assert resp.getheader("Content-Security-Policy") == "default-src 'self'"
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert resp.getheader("Referrer-Policy") == "no-referrer"
    assert resp.getheader("Cache-Control") == "no-store"


def test_samples_listing_is_data_driven(hosted):
    _s, body = hosted.json("GET", "/api/samples")
    ids = [s["id"] for s in body["samples"]]
    assert ids == sorted((*NAMES, NODE_SAMPLE))
    s2 = body["samples"][1]
    assert s2["title"] == "Lost Ledger" and s2["python_files"] == 1
    assert {"path": "requirements.txt", "size": (SAMPLES / NAMES[1] / "requirements.txt").stat().st_size} in s2["files"]


def test_node_sample_is_listed_with_its_files(hosted):
    _s, body = hosted.json("GET", "/api/samples")
    s3 = next(s for s in body["samples"] if s["id"] == NODE_SAMPLE)
    assert s3["title"] == "Ember Ledger" and s3["python_files"] == 0
    assert [f["path"] for f in s3["files"]] == ["README.md", "index.js", "package.json"]


def test_node_sample_source_is_a_node_project():
    assert "EMBER LEDGER ALIVE" in (SAMPLES / NODE_SAMPLE / "index.js").read_text()
    manifest = json.loads((SAMPLES / NODE_SAMPLE / "package.json").read_text())
    assert manifest["engines"]["node"] == "0.10.x" and "node-uuid" in manifest["dependencies"]
    assert not list((SAMPLES / NODE_SAMPLE).rglob("*.py"))


def test_listing_follows_the_directory(tmp_path):
    (tmp_path / "zzz").mkdir()
    (tmp_path / "zzz" / "a.py").write_text("print(1)\n")
    assert [s["id"] for s in srv.list_samples(tmp_path)] == ["zzz"]


@pytest.mark.parametrize("name", NAMES)
def test_autopsy_matches_engine(hosted, name):
    status, body = hosted.json("POST", "/api/autopsy", {"sample": name})
    assert status == 200
    report = autopsy.autopsy(SAMPLES / name)
    assert [f["rule_id"] for f in body["findings"]] == [f.rule_id for f in report.findings]
    assert body["findings"] == json.loads(autopsy.report_json(report))["findings"]
    assert body["summary"]["counts"]["total"] == len(report.findings)
    assert sum(p["count"] for p in body["plan"]) == len(report.findings)
    assert body["cause_of_death"] == [{"category": c, "count": n} for c, n in report.cause_of_death]


def test_hosted_rejects_path_and_upload_and_unknown(hosted, tmp_path):
    assert hosted.json("POST", "/api/autopsy", {"path": str(tmp_path)})[0] == 403
    assert hosted.json("POST", "/api/runs", {"path": str(tmp_path)})[0] == 403
    assert hosted.json("POST", "/api/runs", {"upload": "0" * 32})[0] == 403
    assert hosted.json("POST", "/api/upload", raw=b"x", headers={"Content-Type": "application/zip"})[0] == 403
    assert hosted.json("POST", "/api/runs", {"sample": "nope"})[0] == 404
    assert hosted.json("POST", "/api/runs", {"sample": "../samples"})[0] == 404
    assert hosted.json("POST", "/api/runs", {})[0] == 400
    assert hosted.json("POST", "/api/runs", {"sample": NAMES[0], "path": "/"})[0] == 400


def test_local_path_accepted_and_bad_paths_handled(local, tmp_path):
    repo = tmp_path / "r"
    shutil.copytree(SAMPLES / NAMES[0], repo)
    status, body = local.json("POST", "/api/autopsy", {"path": str(repo)})
    assert status == 200 and body["findings"]
    for bad in (str(tmp_path / "missing"), str(repo / "main.py"), "bad\x00path"):
        status, body = local.json("POST", "/api/autopsy", {"path": bad})
        assert status == 400 and body["error"] == "invalid_path"
    assert local.json("POST", "/api/autopsy", {"path": 5})[0] == 400


def test_host_and_origin_rejected(hosted):
    status, body = hosted.json("GET", "/api/health", headers={"Host": "evil.example"})
    assert status == 403 and body["error"] == "bad_host"
    port = hosted.port
    status, body = hosted.json(
        "POST", "/api/autopsy", {"sample": NAMES[0]}, headers={"Origin": "http://evil.example"}
    )
    assert status == 403 and body["error"] == "bad_origin"
    ok, _ = hosted.json("POST", "/api/autopsy", {"sample": NAMES[0]}, headers={"Origin": f"http://127.0.0.1:{port}"})
    assert ok == 200


def test_content_type_and_body_errors(hosted):
    assert hosted.json("POST", "/api/autopsy", raw=b"{}", headers={"Content-Type": "text/plain"})[0] == 415
    assert hosted.json("POST", "/api/autopsy", raw=b"{nope", headers={"Content-Type": "application/json"})[0] == 400
    assert hosted.json("POST", "/api/autopsy", raw=b"[1]", headers={"Content-Type": "application/json"})[0] == 400
    big = b'{"sample": "' + b"a" * 70000 + b'"}'
    assert hosted.json("POST", "/api/autopsy", raw=big, headers={"Content-Type": "application/json"})[0] == 413
    assert hosted.json("POST", "/api/runs", {"sample": NAMES[0], "prove": "yes"})[0] == 400
    status, body = hosted.json("GET", "/api/nope")
    assert status == 404 and set(body) == {"error", "detail"}
    assert hosted.json("PUT", "/api/runs")[0] == 501
    # the server survives all of the above
    assert hosted.json("GET", "/api/health")[0] == 200


def test_static_serving_and_traversal(hosted):
    resp, body = hosted.request("GET", "/")
    assert resp.status == 200 and b"Grimoire" in body and resp.getheader("Content-Type").startswith("text/html")
    for path in ("/../pyproject.toml", "/%2e%2e/pyproject.toml", "/..%2fpyproject.toml", "/server.py", "/__init__.py", "//etc/passwd"):
        assert hosted.request("GET", path)[0].status == 404, path


@pytest.mark.parametrize("name", NAMES)
def test_run_reaches_success_equal_to_direct_revive(hosted, name):
    status, body = hosted.json("POST", "/api/runs", {"sample": name})
    assert status == 202
    snap = hosted.wait_run(body["run_id"])
    assert snap["state"] == "done"
    result = snap["result"]
    assert result["outcome"] == "SUCCESS"
    direct = revive.revive(SAMPLES / name, prove=True, wheelhouse=WHEELHOUSE)
    assert result == json.loads(json.dumps(result_payload(direct)))
    assert result["proof"]["status"] == "ALIVE"
    assert [s["status"] for s in snap["stages"]] == ["done"] * 7
    assert result["stats"]["issues_after"] == 0 and result["stats"]["issues_before"] > 0


def test_sample2_without_wheelhouse_is_partial():
    server = start(srv.Config(mode="hosted", port=0, wheelhouse=None, samples_dir=SAMPLES))
    server.config.wheelhouse = None  # the constructor defaults to the shipped one; force none
    try:
        c = Client(server)
        _s, body = c.json("POST", "/api/runs", {"sample": "sample-legacy-2"})
        snap = c.wait_run(body["run_id"])
        assert snap["result"]["outcome"] == "PARTIAL"
        assert snap["result"]["proof"]["status"] == "UNVERIFIED"
    finally:
        server.shutdown()
        server.server_close()


def test_run_without_prove_is_partial_and_has_no_prove_stage(hosted):
    _s, body = hosted.json("POST", "/api/runs", {"sample": NAMES[0], "prove": False})
    snap = hosted.wait_run(body["run_id"])
    assert snap["result"]["outcome"] == "PARTIAL" and snap["result"]["proof"] is None
    assert "prove" not in [s["name"] for s in snap["stages"]]


def parse_sse(raw):
    events = []
    for block in raw.decode().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "data" in fields:
            events.append((int(fields["id"]), json.loads(fields["data"])))
    return events


def test_sse_order_replay_and_live_proof_lines(hosted):
    _s, body = hosted.json("POST", "/api/runs", {"sample": NAMES[1]})
    run_id = body["run_id"]
    resp, raw = hosted.request("GET", f"/api/runs/{run_id}/events")
    assert resp.getheader("Content-Type").startswith("text/event-stream")
    events = parse_sse(raw)
    assert [i for i, _e in events] == list(range(1, len(events) + 1))
    assert events[-1][1]["type"] == "end" and events[-1][1]["outcome"] == "SUCCESS"
    stages = [e["stage"] for _i, e in events if e["type"] == "stage" and e["status"] == "start"]
    assert stages == ["autopsy", "copy", "repair", "reanalyze", "validate", "dockerfile", "prove"]
    logs = [e["message"] for _i, e in events if e["type"] == "log"]
    assert "LOST LEDGER ALIVE" in logs
    first_log = next(i for i, e in events if e["type"] == "log")
    prove_start = next(i for i, e in events if e["type"] == "stage" and e["stage"] == "prove" and e["status"] == "start")
    prove_done = next(i for i, e in events if e["type"] == "stage" and e["stage"] == "prove" and e["status"] == "done")
    assert prove_start < first_log < prove_done
    snap = hosted.wait_run(run_id)
    assert logs == [l for l in snap["result"]["proof"]["log_lines"] if l]
    # Last-Event-ID resumes after the given event
    _r, raw2 = hosted.request("GET", f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "5"})
    assert [i for i, _e in parse_sse(raw2)] == list(range(6, len(events) + 1))
    assert hosted.json("GET", "/api/runs/" + "0" * 32)[0] == 404
    assert hosted.json("GET", "/api/runs/not-an-id")[0] == 404


def test_too_many_concurrent_runs(hosted):
    server_runs = []
    gate = threading.Event()
    original = revive.revive

    def slow(*a, **k):
        gate.wait(30)
        return original(*a, **k)

    # Block the pipeline thread so runs stay active; this controls timing only.
    revive_mod = srv.revive_mod
    revive_mod.revive = slow
    try:
        for _ in range(srv.MAX_CONCURRENT_RUNS):
            status, body = hosted.json("POST", "/api/runs", {"sample": NAMES[0], "prove": False})
            assert status == 202
            server_runs.append(body["run_id"])
        status, body = hosted.json("POST", "/api/runs", {"sample": NAMES[0], "prove": False})
        assert status == 429 and body["error"] == "too_many_runs"
    finally:
        gate.set()
        revive_mod.revive = original
        for rid in server_runs:
            hosted.wait_run(rid)


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries:
            if isinstance(data, zipfile.ZipInfo):
                zf.writestr(data, "target")
            else:
                zf.writestr(name, data)
    return buf.getvalue()


def upload(client, data):
    return client.json("POST", "/api/upload", raw=data, headers={"Content-Type": "application/zip"})


def test_upload_roundtrip_and_run(local):
    data = make_zip([("main.py", "print 'hi'\n")])
    status, body = upload(local, data)
    assert status == 201
    _s, run = local.json("POST", "/api/runs", {"upload": body["upload_id"]})
    snap = local.wait_run(run["run_id"])
    assert snap["result"]["outcome"] == "SUCCESS"
    assert "hi" in snap["result"]["proof"]["log_lines"]
    assert local.json("POST", "/api/runs", {"upload": "f" * 32})[0] == 404


def test_upload_safety(local):
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    for entries in (
        [("../evil.py", "x")],
        [("/abs.py", "x")],
        [("a/../../evil.py", "x")],
        [("..\\evil.py", "x")],
        [("link", link)],
    ):
        status, body = upload(local, make_zip(entries))
        assert status == 400, entries
    assert upload(local, b"not a zip")[0] == 400
    assert local.json("POST", "/api/upload", raw=b"{}", headers={"Content-Type": "application/json"})[0] == 415


def test_upload_limits(local, monkeypatch):
    monkeypatch.setattr(srv, "UPLOAD_MAX_FILES", 3)
    assert upload(local, make_zip([(f"f{i}.py", "x") for i in range(4)]))[0] == 413
    monkeypatch.setattr(srv, "UPLOAD_CAP", 100)
    assert upload(local, make_zip([("a.py", "x" * 500)]))[0] == 413
    assert upload(local, b"z" * 101)[0] == 413  # body cap, before any parsing


def test_local_refuses_non_loopback_host():
    with pytest.raises(srv.ConfigError):
        srv.DashboardServer(srv.Config(mode="local", host="0.0.0.0", port=0))
    assert not srv.is_loopback("192.168.1.5") and srv.is_loopback("::1")


def test_workspace_removed_on_shutdown():
    server = srv.DashboardServer(srv.Config(mode="local", port=0, samples_dir=SAMPLES))
    ws = server.workspace
    assert ws.is_dir()
    server.server_close()
    assert not ws.exists()


def test_no_sample_names_in_server_source():
    for p in (ROOT / "src" / "grimoire" / "dashboard").glob("*.py"):
        assert "sample-legacy" not in p.read_text()


def test_upload_file_dir_conflict_is_400(local):
    status, body = upload(local, make_zip([("a", "x"), ("a/b.py", "y")]))
    assert status == 400 and body["error"] == "bad_zip"
    status, _ = upload(local, make_zip([("a/b.py", "y"), ("a", "x")]))
    assert status == 400


def test_origin_missing_allowed_but_null_rejected(hosted):
    # Non-browser clients send no Origin and are allowed; browsers always send one cross-origin.
    assert hosted.json("POST", "/api/autopsy", {"sample": NAMES[0]})[0] == 200
    status, body = hosted.json("POST", "/api/autopsy", {"sample": NAMES[0]}, headers={"Origin": "null"})
    assert status == 403 and body["error"] == "bad_origin"


# ------------------------------------------------------------------------------ node support


def test_autopsy_node_flag_matches_engine(hosted):
    _s, off = hosted.json("POST", "/api/autopsy", {"sample": NODE_SAMPLE})
    assert not any(f["rule_id"].startswith("NODE_") for f in off["findings"])
    status, on = hosted.json("POST", "/api/autopsy", {"sample": NODE_SAMPLE, "node": True})
    assert status == 200
    report = autopsy.autopsy(SAMPLES / NODE_SAMPLE, node=True)
    assert on["findings"] == json.loads(autopsy.report_json(report))["findings"]
    assert {f["rule_id"] for f in on["findings"]} >= {"NODE_RENAMED_PACKAGE", "NODE_BAD_RANGE", "NODE_ENGINE_OUTDATED"}
    assert hosted.json("POST", "/api/autopsy", {"sample": NODE_SAMPLE, "node": False})[1] == off


def test_node_flag_must_be_boolean(hosted):
    for path in ("/api/autopsy", "/api/runs"):
        for bad in ("yes", 1, None):
            assert hosted.json("POST", path, {"sample": NODE_SAMPLE, "node": bad})[0] == 400


def test_node_run_shows_package_json_diff(hosted):
    status, body = hosted.json("POST", "/api/runs", {"sample": NODE_SAMPLE, "node": True, "prove": False})
    assert status == 202
    snap = hosted.wait_run(body["run_id"])
    assert snap["state"] == "done" and snap["node"] is True
    result = snap["result"]
    assert [p["path"] for p in result["patches"]] == ["package.json"]
    assert "--- a/package.json" in result["diff"] and "+++ b/package.json" in result["diff"]
    assert '+        "node": ">=18"' in result["diff"]
    assert "--- a/index.js" not in result["diff"]
    assert result["stats"]["issues_after"] == 0
    direct = revive.revive(SAMPLES / NODE_SAMPLE, prove=False, node=True)
    assert result == json.loads(json.dumps(result_payload(direct)))


def test_run_without_node_flag_leaves_package_json(hosted):
    _s, body = hosted.json("POST", "/api/runs", {"sample": NODE_SAMPLE, "prove": False})
    snap = hosted.wait_run(body["run_id"])
    assert snap["node"] is False and snap["result"]["patches"] == []


def test_node_flag_keeps_hosted_allowlist(hosted, tmp_path):
    for path in ("/api/autopsy", "/api/runs"):
        assert hosted.json("POST", path, {"sample": "nope", "node": True})[0] == 404
        assert hosted.json("POST", path, {"path": str(tmp_path), "node": True})[0] == 403
