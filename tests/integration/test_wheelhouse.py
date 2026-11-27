"""The shipped wheelhouse lets both samples reach ALIVE with no network."""

import shutil
from pathlib import Path

import pytest

from grimoire import cli, revive
from tests.integration.test_samples import NAMES, SAMPLES, tree_hash

WHEELHOUSE = Path(__file__).resolve().parents[2] / "wheelhouse"


def test_shipped_wheelhouse_has_real_wheels():
    names = {p.name.split("-")[0] for p in WHEELHOUSE.glob("*.whl")}
    assert {"beautifulsoup4", "soupsieve", "six", "typing_extensions"} <= names
    assert all(p.stat().st_size > 5000 for p in WHEELHOUSE.glob("*.whl"))


@pytest.mark.parametrize("name", NAMES)
def test_both_samples_alive_with_shipped_wheelhouse(name, tmp_path):
    repo = tmp_path / name
    shutil.copytree(SAMPLES / name, repo)
    report = revive.revive(repo, tmp_path / "out", prove=True, wheelhouse=WHEELHOUSE)
    assert report.proof.status == "ALIVE"


def test_sample2_unverified_without_wheelhouse(tmp_path):
    repo = tmp_path / "s2"
    shutil.copytree(SAMPLES / "sample-legacy-2", repo)
    assert revive.revive(repo, prove=True).proof.status == "UNVERIFIED"


def test_cli_prove_exit_codes():
    s2 = str(SAMPLES / "sample-legacy-2")
    assert cli.main(["prove", s2, "--wheelhouse", str(WHEELHOUSE)]) == 0
    assert cli.main(["prove", s2]) == 2


def test_samples_byte_identical_after_runs(tmp_path):
    before = {n: tree_hash(SAMPLES / n) for n in NAMES}
    for n in NAMES:
        revive.revive(SAMPLES / n, tmp_path / n, prove=True, wheelhouse=WHEELHOUSE)
    assert {n: tree_hash(SAMPLES / n) for n in NAMES} == before
