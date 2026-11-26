import re
from pathlib import Path

FORBIDDEN = re.compile(r"^\s*(?:import|from)\s+(?:requests|socket|urllib\.request|urllib2|http\.client|httplib)\b", re.M)


def test_engine_has_no_network_imports():
    src = Path(__file__).resolve().parents[2] / "src" / "grimoire"
    # The dashboard package is a local HTTP server and necessarily uses sockets to listen.
    # It is not part of the engine, which must stay offline. Scope it out here, and nothing else.
    engine = [p for p in src.rglob("*.py") if "dashboard" not in p.relative_to(src).parts]
    offenders = [str(p) for p in engine if FORBIDDEN.search(p.read_text())]
    assert offenders == []
