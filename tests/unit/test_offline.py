import re
from pathlib import Path

FORBIDDEN = re.compile(r"^\s*(?:import|from)\s+(?:requests|socket|urllib\.request|urllib2|http\.client|httplib)\b", re.M)


def test_engine_has_no_network_imports():
    src = Path(__file__).resolve().parents[2] / "src" / "grimoire"
    offenders = [str(p) for p in src.rglob("*.py") if FORBIDDEN.search(p.read_text())]
    assert offenders == []
