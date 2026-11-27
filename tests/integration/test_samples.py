"""End-to-end: the two sample repositories go through the real pipeline, nothing is mocked."""

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from grimoire import autopsy, cli, revive

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"
SRC = ROOT / "src"
NAMES = ("sample-legacy-1", "sample-legacy-2")
SUCCESS = {"sample-legacy-1": "TALLY KEEPER ALIVE", "sample-legacy-2": "LOST LEDGER ALIVE"}


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def build_wheel(dest: Path, dist: str, version: str, module: str, code: str) -> None:
    """Build a minimal real wheel with stdlib zipfile."""
    info = f"{dist}-{version}.dist-info"
    files = {
        f"{module}.py": code,
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {dist}\nVersion: {version}\n",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    files[f"{info}/RECORD"] = "".join(f"{n},,\n" for n in files) + f"{info}/RECORD,,\n"
    with zipfile.ZipFile(dest / f"{dist}-{version}-py3-none-any.whl", "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)


@pytest.fixture(scope="module")
def wheelhouse(tmp_path_factory):
    wh = tmp_path_factory.mktemp("wheelhouse")
    build_wheel(wh, "six", "1.16.0", "six", "string_types = (str,)\n")
    build_wheel(wh, "beautifulsoup4", "4.12.0", "bs4", "__version__ = '4.12.0'\n")
    return wh


@pytest.fixture
def sample(request, tmp_path):
    name = request.param
    dst = tmp_path / name
    shutil.copytree(SAMPLES / name, dst)
    return name, dst


def run_py(path: Path):
    return subprocess.run([sys.executable, "main.py"], cwd=path, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("sample", NAMES, indirect=True)
def test_sample_dead_before_alive_after(sample, wheelhouse, tmp_path):
    name, repo = sample
    assert run_py(repo).returncode != 0
    before_hash = tree_hash(repo)

    report = revive.revive(repo, tmp_path / "out", prove=True, wheelhouse=wheelhouse)

    assert tree_hash(repo) == before_hash, "source repository must stay untouched"
    assert report.before_findings and any(f.repair_class == "AUTOMATIC" for f in report.before_findings)
    assert report.patches
    assert report.findings == ()
    assert all(status == "PASS" for _n, status, _d in report.validation)
    assert report.proof.status == "ALIVE"
    assert any(SUCCESS[name] in line for line in report.proof.log_lines)

    out = tmp_path / "out"
    assert autopsy.autopsy(out).findings == ()
    result = run_py(out)  # recovered files, run with the interpreter running the tests
    if name == "sample-legacy-1":
        assert result.returncode == 0 and SUCCESS[name] in result.stdout
    assert (out / ".grimoire-backup" / "main.py").read_bytes() == (SAMPLES / name / "main.py").read_bytes()


def test_sample2_requirements_recovered(tmp_path, wheelhouse):
    repo = tmp_path / "s2"
    shutil.copytree(SAMPLES / "sample-legacy-2", repo)
    revive.revive(repo, tmp_path / "out")
    assert (tmp_path / "out" / "requirements.txt").read_text() == "beautifulsoup4\nsix\n"


def test_sample2_unverified_without_wheelhouse(tmp_path):
    repo = tmp_path / "s2"
    shutil.copytree(SAMPLES / "sample-legacy-2", repo)
    assert revive.revive(repo, prove=True).proof.status == "UNVERIFIED"


@pytest.mark.parametrize("sample", NAMES, indirect=True)
def test_second_run_is_idempotent(sample, tmp_path):
    _name, repo = sample
    out1, out2 = tmp_path / "o1", tmp_path / "o2"
    revive.revive(repo, out1)
    again = revive.revive(out1, out2)
    assert again.patches == () and again.diff == ""
    ignore = lambda p: ".grimoire-backup" in p.parts
    files = lambda d: {p.relative_to(d): p.read_bytes() for p in d.rglob("*") if p.is_file() and not ignore(p.relative_to(d))}
    assert files(out1) == files(out2)


@pytest.mark.parametrize("sample", NAMES, indirect=True)
def test_cli_exit_codes(sample, wheelhouse, tmp_path):
    name, repo = sample
    assert cli.main(["autopsy", str(repo)]) == 0  # autopsy reports, it does not fail on findings
    assert cli.main(["revive", str(repo), "--output", str(tmp_path / "o")]) == 0
    assert cli.main(["prove", str(repo), "--wheelhouse", str(wheelhouse)]) == 0


def test_no_sample_specific_logic_in_src():
    offenders = [
        str(p)
        for p in SRC.rglob("*")
        if p.is_file() and p.suffix in {".py", ".json"}
        and any(s in p.read_text(encoding="utf-8") for s in ("sample-legacy", "TALLY KEEPER", "LOST LEDGER"))
    ]
    assert offenders == []
