"""Static checks on the dashboard front end: CSP safety, wiring, routes, packaging."""

import re
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path

import pytest

from grimoire.dashboard import server as srv

STATIC = Path(srv.__file__).parent / "static"
FILES = ["index.html", "app.css", "app.js", "lib.js"]
JS = ["app.js", "lib.js"]


def text(name):
    return (STATIC / name).read_text(encoding="utf-8")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.controls = []  # (tag, attrs)
        self.inline_scripts = 0
        self.style_attrs = 0
        self.style_tags = 0
        self.handler_attrs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag in ("button", "select", "textarea") or (tag == "input"):
            self.controls.append((tag, a))
        if tag == "script" and "src" not in a:
            self.inline_scripts += 1
        if tag == "style":
            self.style_tags += 1
        if "style" in a:
            self.style_attrs += 1
        self.handler_attrs += [k for k in a if k.startswith("on")]


def page():
    p = Page()
    p.feed(text("index.html"))
    return p


@pytest.mark.parametrize("name", FILES)
def test_no_external_urls(name):
    body = text(name)
    assert not re.search(r"https?://", body), "external URL found"
    # protocol-relative URLs in attribute or string position
    assert not re.search(r"""(src|href|url\(|action)\s*=?\s*["']?//""", body)


@pytest.mark.parametrize("name", JS)
def test_no_dangerous_js_apis(name):
    body = text(name)
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "document.write", "new Function", "setAttribute(\"style\"", "setAttribute('style'"):
        assert bad not in body, f"{bad} in {name}"
    assert not re.search(r"set(Timeout|Interval)\(\s*[\"']", body)


def test_index_is_csp_clean():
    p = page()
    assert p.inline_scripts == 0
    assert p.style_tags == 0
    assert p.style_attrs == 0
    assert p.handler_attrs == []


def test_semantic_landmarks():
    html = text("index.html")
    for tag in ("<header", "<main", "<nav", "<footer", 'lang="en"', 'name="viewport"'):
        assert tag in html
    assert html.count("aria-live") >= 2


def test_ids_used_by_app_exist_in_index():
    ids = page().ids
    used = set(re.findall(r"""\$\(\s*["']([\w-]+)["']\s*\)""", text("app.js")))
    used |= set(re.findall(r"""getElementById\(\s*["']([\w-]+)["']""", text("app.js")))
    assert used, "no ids found"
    assert used <= ids, f"missing ids: {sorted(used - ids)}"
    # ids built from a prefix: view-<name>, panel-<name>
    app = text("app.js")
    for prefix, names in (("view-", ("diff", "before", "after")), ("panel-", ("diff", "dockerfile", "validation", "proof"))):
        assert prefix in app
        for n in names:
            assert prefix + n in ids
    for lst in re.findall(r"\[((?:\s*\"[\w-]+\"\s*,?)+)\]\.forEach", app):
        for ident in re.findall(r'"([\w-]+)"', lst):
            if ident.startswith(("path-", "zip-", "filter-", "drop-")):
                assert ident in ids


def test_every_control_has_a_handler():
    p = page()
    app = text("app.js")
    assert p.controls
    for tag, a in p.controls:
        if tag == "input" and a.get("type") == "hidden":
            continue
        ident = a.get("id")
        assert ident, f"control without id: {a}"
        referenced = f'"{ident}"' in app or f"'{ident}'" in app
        if not referenced:
            # group handlers keyed by data attributes
            data = [k for k in a if k.startswith("data-")]
            assert data and any(f"[{k}]" in app for k in data), f"no handler for #{ident}"


def test_error_banner_buttons_and_dropzone_wired():
    app = text("app.js")
    for ident in ("error-retry", "error-dismiss", "drop-zone", "download-btn", "copy-log-btn"):
        assert f'"{ident}"' in app
    assert "dragover" in app and "drop" in app


def test_api_routes_used_by_js_exist_on_server():
    app = text("app.js")
    paths = set(re.findall(r'"(/api/[\w/]*)"', app))
    assert {"/api/health", "/api/samples", "/api/autopsy", "/api/runs", "/api/upload"} <= paths
    server_src = Path(srv.__file__).read_text(encoding="utf-8")
    for route in paths:
        assert route.rstrip("/") in server_src, route
    assert '"/api/runs/"' in app and "/events" in app
    assert re.search(r"/api/runs/\(\[0-9a-f\]\{32\}\)\(/events\)\?", server_src)


def test_static_files_are_allowlisted_and_present():
    assert set(FILES) == set(srv.STATIC_FILES)
    for name in FILES:
        assert (STATIC / name).stat().st_size > 0


def test_index_references_only_allowlisted_local_assets():
    html = text("index.html")
    refs = re.findall(r'(?:src|href)="([^"#][^"]*)"', html)
    for ref in refs:
        assert ref.lstrip("/") in srv.STATIC_FILES, ref


def test_static_files_are_package_data():
    base = resources.files("grimoire").joinpath("dashboard", "static")
    for name in FILES:
        assert base.joinpath(name).is_file(), name
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    assert "dashboard/static/*" in pyproject
