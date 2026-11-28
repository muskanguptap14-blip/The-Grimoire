import hashlib
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from grimoire import autopsy, cli, revive, verify
from grimoire.revive import OutputError

PY2_MAIN = 'import os\nprint "hello"\ntry:\n    pass\nexcept Exception, e:\n    print e\n'


def make_repo(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())
    return root


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "repo", {"main.py": PY2_MAIN, "requirements.txt": "# none\n"})


def test_source_untouched_and_before_after(repo):
    h = tree_hash(repo)
    report = revive.revive(repo)
    assert tree_hash(repo) == h
    assert report.before_findings and report.findings == ()
    assert [p.path for p in report.patches] == ["main.py"]
    assert "-print \"hello\"" in report.diff and "+print(\"hello\")" in report.diff
    assert all(s == "PASS" for _n, s, _d in report.validation)
    assert "CMD" in report.dockerfile and "main.py" in report.dockerfile


def test_revive_twice_identical_reports(repo):
    assert revive.revive(repo) == revive.revive(repo)


def test_idempotent_revive_of_revived_output(repo, tmp_path):
    out = tmp_path / "out"
    revive.revive(repo, out)
    again = revive.revive(out)
    assert again.patches == () and again.diff == ""
    out2 = tmp_path / "out2"
    revive.revive(out, out2)
    assert (out / "main.py").read_bytes() == (out2 / "main.py").read_bytes()


def test_output_writes_backups_and_dockerfile(repo, tmp_path):
    out = tmp_path / "out"
    h = tree_hash(repo)
    revive.revive(repo, out)
    assert tree_hash(repo) == h
    assert (out / ".grimoire-backup" / "main.py").read_bytes() == PY2_MAIN.encode()
    assert "print(" in (out / "main.py").read_text()
    assert (out / "Dockerfile.grimoire").read_text().startswith("FROM python:3.11-slim")


def test_missing_dependency_added_to_requirements(tmp_path):
    repo = make_repo(tmp_path / "r", {"main.py": "import requests\n", "requirements.txt": "flask\n"})
    report = revive.revive(repo)
    assert report.findings == ()
    assert any(p.path == "requirements.txt" for p in report.patches)


def test_existing_empty_output_dir_is_accepted(repo, tmp_path):
    out = tmp_path / "empty"
    out.mkdir()
    revive.revive(repo, out)
    assert (out / "Dockerfile.grimoire").exists()
    assert (out / ".grimoire-backup" / "main.py").exists()


@pytest.mark.parametrize("pre_existing", [False, True])
def test_failed_persist_leaves_no_partial_output(repo, tmp_path, monkeypatch, pre_existing):
    out = tmp_path / "out"
    if pre_existing:
        out.mkdir()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(revive.Path, "write_text", boom)
    with pytest.raises(OSError):
        revive.revive(repo, out)
    assert not out.exists() or list(out.iterdir()) == []
    monkeypatch.undo()
    revive.revive(repo, out)
    assert (out / "Dockerfile.grimoire").exists()


@pytest.mark.parametrize("bad", ["inside", "same", "parent", "nonempty"])
def test_unsafe_output_refused(repo, tmp_path, bad):
    target = {
        "inside": repo / "sub",
        "same": repo,
        "parent": tmp_path,
        "nonempty": tmp_path / "ne",
    }[bad]
    if bad == "nonempty":
        target.mkdir()
        (target / "x").write_text("keep")
    h = tree_hash(repo)
    with pytest.raises(OutputError):
        revive.revive(repo, target)
    assert tree_hash(repo) == h
    if bad == "nonempty":
        assert (target / "x").read_text() == "keep"


def test_invalid_repo_is_finding(tmp_path):
    report = revive.revive(tmp_path / "missing")
    assert [f.rule_id for f in report.findings] == ["INVALID_REPO"]


def test_unparseable_file_is_not_claimed_fixed(tmp_path):
    repo = make_repo(tmp_path / "r", {"main.py": "def (:\n"})
    report = revive.revive(repo, prove=True)
    assert any(f.rule_id == "UNPARSEABLE" for f in report.findings)
    assert report.proof.status == "STILL_DEAD"
    assert any(s == "FAIL" for _n, s, _d in report.validation)


def test_revived_project_is_alive(repo):
    report = revive.revive(repo, prove=True)
    assert report.proof.status == "ALIVE", report.proof
    assert report.proof.log_lines == ("hello",)


def test_offline_pipeline_with_socket_blocked(repo, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    assert revive.revive(repo, prove=True).proof.status == "ALIVE"
    assert not autopsy.autopsy(repo).findings == ()


def test_forbidden_imports_absent():
    src = Path(__file__).resolve().parents[2] / "src" / "grimoire"
    for p in src.rglob("*.py"):
        if "dashboard" in p.relative_to(src).parts:
            continue  # the dashboard is a local HTTP server, outside the offline engine; it needs sockets to listen
        text = p.read_text()
        for bad in ("import socket", "import requests", "urllib.request", "http.client", "import urllib2"):
            assert bad not in text, (p, bad)


# verifier statuses


def test_verify_still_dead(tmp_path):
    repo = make_repo(tmp_path / "r", {"main.py": "raise SystemExit(3)\n"})
    r = verify.verify(repo, "main.py")
    assert (r.status, r.exit_code) == ("STILL_DEAD", 3)


def test_verify_timed_out_and_cleanup(tmp_path, monkeypatch):
    tmpdir = tmp_path / "scratch"
    tmpdir.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(tmpdir))
    repo = make_repo(tmp_path / "r", {"main.py": "import time\ntime.sleep(60)\n"})
    r = verify.verify(repo, "main.py", timeout=1)
    assert r.status == "TIMED_OUT"
    assert list(tmpdir.iterdir()) == []


def test_verify_unverified_without_wheelhouse(tmp_path):
    repo = make_repo(tmp_path / "r", {"main.py": "print(1)\n", "requirements.txt": "left-pad-nope\n"})
    r = verify.verify(repo, "main.py")
    assert r.status == "UNVERIFIED" and "left-pad-nope" in r.log_lines[0]


def test_verify_unverified_when_wheelhouse_lacks_package(tmp_path):
    repo = make_repo(tmp_path / "r", {"main.py": "print(1)\n", "requirements.txt": "left-pad-nope\n"})
    (tmp_path / "wh").mkdir()
    assert verify.verify(repo, "main.py", wheelhouse=tmp_path / "wh").status == "UNVERIFIED"


def test_verify_unverified_without_entry(tmp_path):
    repo = make_repo(tmp_path / "r", {"lib.py": "x = 1\n"})
    assert verify.verify(repo, None).status == "UNVERIFIED"


def test_verify_output_capped(tmp_path):
    repo = make_repo(tmp_path / "r", {"main.py": "import sys\nsys.stdout.write('x' * 3000000)\n"})
    r = verify.verify(repo, "main.py")
    assert r.status == "ALIVE" and sum(len(l) for l in r.log_lines) <= verify.OUTPUT_CAP


def test_verify_env_is_minimal(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIMOIRE_SECRET", "s3cret")
    repo = make_repo(tmp_path / "r", {"main.py": "import os\nprint(os.environ.get('GRIMOIRE_SECRET'))\n"})
    assert verify.verify(repo, "main.py").log_lines == ("None",)


# CLI


def test_cli_exit_codes(repo, tmp_path, capsys):
    assert cli.main(["autopsy", str(repo)]) == 0
    assert cli.main(["autopsy", str(tmp_path / "nope")]) == 3
    assert cli.main(["prove", str(repo)]) == 0
    assert cli.main(["prove", str(tmp_path / "nope")]) == 3
    # serve is implemented; a refused configuration (non-loopback local mode) still exits 3
    assert cli.main(["serve", "--mode", "local", "--host", "0.0.0.0", "--port", "0"]) == 3
    assert cli.main(["bogus"]) == 3
    dead = make_repo(tmp_path / "dead", {"main.py": "raise SystemExit(1)\n"})
    assert cli.main(["prove", str(dead)]) == 1
    unv = make_repo(tmp_path / "unv", {"main.py": "print(1)\n", "requirements.txt": "nopkg-xyz\n"})
    assert cli.main(["prove", str(unv)]) == 2
    assert cli.main(["revive", str(repo), "--output", str(repo)]) == 3


def test_cli_json_and_module(repo):
    env = {**os.environ}
    p = subprocess.run([sys.executable, "-m", "grimoire", "revive", str(repo), "--json"], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    import json

    assert json.loads(p.stdout)["findings"] == []
    q = subprocess.run([sys.executable, "-m", "grimoire", "revive", str(repo), "--json"], capture_output=True, text=True, env=env)
    assert p.stdout == q.stdout
