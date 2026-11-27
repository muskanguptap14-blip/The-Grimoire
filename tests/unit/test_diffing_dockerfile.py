from grimoire.diffing import unified_diff
from grimoire.dockerfile import detect_entry, generate_dockerfile
from grimoire.models import FilePatch


def test_diff_sorted_and_no_newline_marker():
    d = unified_diff([FilePatch("b.py", "x", "y"), FilePatch("a.py", "1\n", "2\n"), FilePatch("c.py", "s", "s")])
    assert d.index("a/a.py") < d.index("a/b.py")
    assert "c.py" not in d and "No newline at end of file" in d


def test_entry_order_and_toml(tmp_path):
    (tmp_path / "app.py").write_text("")
    (tmp_path / "main.py").write_text("")
    assert detect_entry(tmp_path) == "main.py"
    (tmp_path / "tool.py").write_text("")
    (tmp_path / "grimoire.toml").write_text('entry = "tool.py"\n')
    assert detect_entry(tmp_path) == "tool.py"
    (tmp_path / "grimoire.toml").write_text('entry = "../evil.py"\n')
    assert detect_entry(tmp_path) == "main.py"


def test_dockerfile_text():
    assert generate_dockerfile("main.py", True) == (
        "FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\n"
        "RUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nCMD [\"python\", \"main.py\"]\n"
    )
    assert "requirements" not in generate_dockerfile("main.py", False)
