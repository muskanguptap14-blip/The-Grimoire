"""Checks for plain repository files: wheelhouse checksums, pytest.ini, save hook."""
import configparser
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_wheelhouse_checksums_match():
    wheelhouse = ROOT / "wheelhouse"
    entries = {}
    for line in (wheelhouse / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        entries[name.strip().lstrip("*")] = digest
    wheels = {p.name for p in wheelhouse.glob("*.whl")}
    assert wheels and set(entries) == wheels
    for name, digest in entries.items():
        assert hashlib.sha256((wheelhouse / name).read_bytes()).hexdigest() == digest, name


def test_pytest_ini_excludes_samples():
    cfg = configparser.ConfigParser()
    cfg.read(ROOT / "pytest.ini")
    assert cfg["pytest"]["testpaths"].strip() == "tests"
    assert "samples" in cfg["pytest"]["norecursedirs"].split()


def test_pytest_on_save_hook_config():
    hook = json.loads((ROOT / ".kiro/hooks/pytest-on-save.json").read_text())["hooks"][0]
    assert hook["trigger"] == "PostFileSave"
    assert hook["action"]["command"] == "python -m pytest -q -x"
    matcher = re.compile(hook["matcher"])
    for path in ("src/grimoire/cli.py", "tests/unit/test_x.py", "tests\\unit\\test_x.py"):
        assert matcher.search(path), path
    for path in ("samples/sample-legacy-1/main.py", "README.md", "src/grimoire/data/x.json"):
        assert not matcher.search(path), path
