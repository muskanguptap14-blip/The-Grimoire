import os

import pytest

from grimoire import scan


def write(root, rel, text="x = 1\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_scan_sorted_and_ignores_dirs(tmp_path):
    for rel in ["b.py", "a.py", "pkg/z.py", "pkg/a.py", "requirements.txt", ".git/x.py", "venv/x.py",
                ".venv/x.py", "node_modules/x.py", "pkg/__pycache__/x.py", "notes.txt"]:
        write(tmp_path, rel)
    result = scan.scan_repo(tmp_path)
    assert [f.path for f in result.files] == ["a.py", "b.py", "pkg/a.py", "pkg/z.py", "requirements.txt"]
    assert result.project_types == ("python",)


def test_language_and_project_detection(tmp_path):
    write(tmp_path, "app.py")
    write(tmp_path, "web/index.js", "var a;")
    write(tmp_path, "package.json", "{}")
    write(tmp_path, "lib.go", "package x")
    result = scan.scan_repo(tmp_path)
    assert dict(result.languages) == {"python": 1, "javascript": 1, "go": 1}
    assert result.project_types == ("node", "python")
    assert scan.detect_language("A/B.PY") == "python"
    assert scan.detect_language("README") == ""


def test_scan_is_deterministic(tmp_path):
    for rel in ["c.py", "a/b.py", "a/a.py"]:
        write(tmp_path, rel)
    assert scan.scan_repo(tmp_path) == scan.scan_repo(tmp_path)


def test_invalid_root_is_a_finding(tmp_path):
    result = scan.scan_repo(tmp_path / "missing")
    assert result.files == () and result.findings[0].rule_id == "INVALID_REPO"


def test_symlink_escape_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("x = 1\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo, "ok.py")
    os.symlink(outside / "secret.py", repo / "link.py")
    os.symlink(outside, repo / "linkdir")
    result = scan.scan_repo(repo)
    assert [f.path for f in result.files] == ["ok.py"]
    assert sorted(f.file for f in result.findings) == ["link.py", "linkdir"]
    assert all(f.rule_id == "SYMLINK_ESCAPE" for f in result.findings)


@pytest.mark.parametrize("rel", ["../x.py", "a/../../x.py", "/etc/passwd", "", "a\x00b"])
def test_path_traversal_rejected(tmp_path, rel):
    with pytest.raises(scan.PathEscapeError):
        scan.resolve_in_repo(tmp_path, rel)


def test_resolve_rejects_escaping_symlink(tmp_path):
    outside = tmp_path / "o"
    outside.mkdir()
    repo = tmp_path / "r"
    repo.mkdir()
    os.symlink(outside, repo / "l")
    with pytest.raises(scan.PathEscapeError):
        scan.resolve_in_repo(repo, "l/x.py")


def test_read_source_errors_become_findings(tmp_path):
    (tmp_path / "bin.py").write_bytes(b"\x00\x01")
    (tmp_path / "latin.py").write_bytes(b"s = '\xe9'\n")
    (tmp_path / "cookie.py").write_bytes(b"# -*- coding: latin-1 -*-\ns = '\xe9'\n")
    (tmp_path / "badcookie.py").write_bytes(b"# coding: nope-9\nx = 1\n")
    src, err = scan.read_source(tmp_path, "bin.py")
    assert src is None and err.rule_id == "BAD_ENCODING"
    src, err = scan.read_source(tmp_path, "latin.py")
    assert src is None and err.rule_id == "BAD_ENCODING" and err.line == 1
    src, err = scan.read_source(tmp_path, "cookie.py")
    assert err is None and src.encoding == "iso-8859-1" and "\xe9" in src.text
    src, err = scan.read_source(tmp_path, "badcookie.py")
    assert src is None and err.rule_id == "BAD_ENCODING"
    src, err = scan.read_source(tmp_path, "missing.py")
    assert src is None and err.rule_id == "UNREADABLE"
    src, err = scan.read_source(tmp_path, "../x.py")
    assert src is None and err.rule_id == "UNREADABLE"


def test_read_source_preserves_line_endings(tmp_path):
    (tmp_path / "crlf.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    src, _ = scan.read_source(tmp_path, "crlf.py")
    assert src.text == "x = 1\r\ny = 2\r\n"
