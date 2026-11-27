import ast
import json
from importlib import resources

import pytest

from grimoire import imports
from grimoire.codemods import apply_all


def rewrite(src):
    result = apply_all(src, "a.py")
    return src if result.patch is None else result.patch.after


@pytest.mark.parametrize(
    "src,expected",
    [
        ("import ConfigParser\n", "import configparser\n"),
        ("import Queue as q\n", "import queue as q\n"),
        ("from StringIO import StringIO\n", "from io import StringIO\n"),
        ("from urllib2 import urlopen, URLError\n", "from urllib.request import urlopen; from urllib.error import URLError\n"),
        ("import os, cPickle\n", "import os, pickle\n"),
        ("import urllib2\nurllib2.urlopen(u)\n", "import urllib.request\nurllib.request.urlopen(u)\n"),
        ("import urllib2\nurllib2.urlopen(a)\nurllib2.URLError\n",
         "import urllib.request, urllib.error\nurllib.request.urlopen(a)\nurllib.error.URLError\n"),
        ("import ConfigParser\nConfigParser.SafeConfigParser()\n", "import configparser\nconfigparser.ConfigParser()\n"),
        ("from ConfigParser import SafeConfigParser\n", "from configparser import ConfigParser as SafeConfigParser\n"),
        ("import cPickle as pickle\n", "import pickle\n"),
        ("import urlparse\nurlparse.urljoin(a, b)\n", "import urllib.parse\nurllib.parse.urljoin(a, b)\n"),
        ("from . import x\n", "from . import x\n"),
        ("import json\n", "import json\n"),
    ],
)
def test_rewrite_forms(src, expected):
    assert rewrite(src) == expected


def test_try_except_fallback_stays_valid():
    src = "try:\n    import cPickle as pickle\nexcept ImportError:\n    import pickle\n"
    out = rewrite(src)
    ast.parse(out)
    assert "cPickle" not in out
    assert rewrite(out) == out


def test_idempotent_and_no_old_names():
    src = "import urllib2, ConfigParser, Queue\nfrom StringIO import StringIO\nurllib2.urlopen(1)\n"
    out = rewrite(src)
    assert rewrite(out) == out
    modules = {r.module.split(".")[0] for r in imports.collect_imports(ast.parse(out))}
    assert not modules & set(imports.load_imports_map())


def test_collect_imports_guarded_and_relative():
    tree = ast.parse("import a\ntry:\n    import b\nexcept ImportError:\n    import c\nfrom . import d\nfrom ..e import f\n")
    refs = {(r.module, r.level, r.guarded) for r in imports.collect_imports(tree)}
    assert refs == {("a", 0, False), ("b", 0, True), ("c", 0, False), ("", 1, False), ("e", 2, False)}


def test_imports_map_shape():
    table = json.loads(resources.files("grimoire").joinpath("data/imports_map.json").read_text())
    import sys

    keys = list(table)
    assert len(keys) == len(set(keys))
    for old, entry in table.items():
        assert entry["new"] and isinstance(entry["new"], str)
        assert entry["new"].split(".")[0] in sys.stdlib_module_names, old
        # targets must never be mapped again (idempotency)
        assert entry["new"] not in table and entry["new"].split(".")[0] not in table
        for attr, target in entry["attrs"].items():
            assert attr and target.count(".") >= 1
            assert target.split(".")[0] in sys.stdlib_module_names


def test_duplicate_json_keys_rejected():
    def no_dupes(pairs):
        keys = [k for k, _ in pairs]
        assert len(keys) == len(set(keys)), keys
        return dict(pairs)

    for name in ("imports_map.json", "packages_map.json"):
        json.loads(resources.files("grimoire").joinpath(f"data/{name}").read_text(), object_pairs_hook=no_dupes)
