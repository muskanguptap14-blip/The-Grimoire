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


GOLDEN = __import__("pathlib").Path(__file__).resolve().parents[1] / "golden" / "dockerfile"
REPO_ROOT = GOLDEN.parents[2]


def _golden(name):
    return (GOLDEN / name).read_text(encoding="utf-8")


def test_golden_python_dockerfile():
    assert generate_dockerfile("main.py", True) == _golden("python-requirements.Dockerfile")


def test_golden_node_dockerfile():
    from grimoire.dockerfile import generate_node_dockerfile

    assert generate_node_dockerfile("index.js") == _golden("node-default.Dockerfile")
    assert generate_node_dockerfile("server/start.js") == _golden("node-custom-main.Dockerfile")


def test_node_main_detection(tmp_path):
    from grimoire.dockerfile import detect_node_main

    def main_for(text):
        (tmp_path / "package.json").write_text(text)
        return detect_node_main(tmp_path)

    assert main_for('{"main": "server/start.js"}') == "server/start.js"
    assert main_for('{"main": "./lib/app.js"}') == "lib/app.js"
    for bad in ('{}', '{"main": 3}', '{"main": ""}', '{"main": "../x.js"}', '{"main": "/etc/x.js"}', "not json", "[]"):
        assert main_for(bad) == "index.js"


def test_node_only_detection(tmp_path):
    from grimoire.dockerfile import is_node_only

    assert not is_node_only(tmp_path)
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "index.js").write_text("")
    assert is_node_only(tmp_path)
    (tmp_path / "tool.py").write_text("")
    assert not is_node_only(tmp_path)


def test_revive_node_only_golden(tmp_path):
    from grimoire import revive

    report = revive.revive(REPO_ROOT / "samples" / "sample-legacy-3", node=True)
    assert report.dockerfile == _golden("node-default.Dockerfile")
    report = revive.revive(REPO_ROOT / "tests" / "fixtures" / "node-legacy", node=True)
    assert report.dockerfile == _golden("node-default.Dockerfile")
    # Without Node support the old behavior is unchanged.
    assert revive.revive(REPO_ROOT / "samples" / "sample-legacy-3").dockerfile.startswith("FROM python:3.11-slim")


def test_revive_custom_main_and_mixed(tmp_path):
    from grimoire import revive

    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0", "main": "server/start.js"}\n')
    assert revive.revive(tmp_path, node=True).dockerfile == _golden("node-custom-main.Dockerfile")
    (tmp_path / "main.py").write_text("print('hi')\n")
    mixed = revive.revive(tmp_path, node=True).dockerfile
    assert mixed == 'FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nCMD ["python", "main.py"]\n'


def test_revive_python_sample_golden():
    from grimoire import revive

    report = revive.revive(REPO_ROOT / "samples" / "sample-legacy-1", node=True)
    assert report.dockerfile == revive.revive(REPO_ROOT / "samples" / "sample-legacy-1").dockerfile
    assert report.dockerfile.startswith("FROM python:3.11-slim\n")


def test_golden_node_dockerignore(tmp_path):
    from grimoire import revive
    from grimoire.dockerfile import generate_node_dockerignore

    assert generate_node_dockerignore() == _golden("node.dockerignore")
    report = revive.revive(REPO_ROOT / "samples" / "sample-legacy-3", node=True)
    assert report.dockerignore == _golden("node.dockerignore")
    out = tmp_path / "out"
    revive.revive(REPO_ROOT / "samples" / "sample-legacy-3", node=True, output=out)
    assert (out / ".dockerignore").read_text(encoding="utf-8") == _golden("node.dockerignore")
    assert (out / "Dockerfile.grimoire").read_text(encoding="utf-8") == _golden("node-default.Dockerfile")


def test_no_dockerignore_for_python(tmp_path):
    from grimoire import revive

    out = tmp_path / "out"
    report = revive.revive(REPO_ROOT / "samples" / "sample-legacy-1", node=True, output=out)
    assert report.dockerignore == ""
    assert not (out / ".dockerignore").exists()
