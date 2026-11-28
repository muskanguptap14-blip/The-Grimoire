"""Stdlib-only property checks for the package.json fixer.

Kept free of Hypothesis so the same checks run under ``test_nodejs_properties.py`` and
under any plain random loop.
"""

from __future__ import annotations

import json

from grimoire import nodejs

SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")


def _key_orders(node, prefix=()):
    if isinstance(node, dict):
        yield prefix, list(node)
        for key, value in node.items():
            yield from _key_orders(value, prefix + (key,))


def check_manifest(manifest: dict, indent: int | str | None) -> None:
    """Assert every Req 10.3 property for one manifest."""
    text = json.dumps(manifest, indent=indent)
    out, findings = nodejs.fix_manifest(text)

    # output is valid JSON
    result = json.loads(out)

    # key order is preserved at every level (no key is added, removed or moved)
    assert dict(_key_orders(result)) == dict(_key_orders(manifest))

    # idempotent: a second pass changes nothing and finds nothing automatic
    again, again_findings = nodejs.fix_manifest(out)
    assert again == out
    assert not [f for f in again_findings if f.repair_class == "AUTOMATIC"]

    # deterministic
    assert nodejs.fix_manifest(text) == (out, findings)

    # nothing outside dependency sections and engines.node changed
    for key, value in manifest.items():
        if key not in SECTIONS and key != "engines":
            assert result[key] == value
    engines = manifest.get("engines")
    if isinstance(engines, dict):
        for key, value in engines.items():
            if key != "node":
                assert result["engines"][key] == value

    # untouched manifests are returned byte for byte
    if not [f for f in findings if f.repair_class == "AUTOMATIC"]:
        assert out == text
    else:
        assert out != text
