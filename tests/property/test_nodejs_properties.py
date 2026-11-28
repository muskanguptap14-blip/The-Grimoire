"""[PBT] Task 29: the package.json fixer is idempotent, order preserving and always valid JSON."""

from hypothesis import given, strategies as st

from grimoire import nodejs

from nodejs_checks import SECTIONS, check_manifest

_table = nodejs.load_node_map()
_names = st.sampled_from(
    sorted(_table["renames"]) + sorted(_table["deprecated"]) + sorted(_table["bad_ranges"]) + ["express", "left_alone", "@scope/pkg"]
)
_specs = st.one_of(
    st.sampled_from(
        [
            "*", "1.x", "^0.2.3", "~1.2.3", "1.2.3", ">=1.0.0 <3", "<2", "<=2.1", "^1.0.0 || ^2.0.0",
            "latest", "git+https://example.com/x.git", "file:../x", "npm:other@^1.0.0", "1.2.3 - 2.3.4",
            "^3.10.1", "~1.11.0", "^4.17.21", "^1.2.13", "^2.3.2", "0.10.x", ">=18", "^16", "<=14",
        ]
    ),
    st.from_regex(r"[\^~]?[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}", fullmatch=True),
)
_section = st.dictionaries(_names, _specs, max_size=6)
_extra = st.dictionaries(
    st.sampled_from(["name", "version", "main", "scripts", "files", "keywords"]),
    st.one_of(st.text(max_size=12), st.lists(st.text(max_size=5), max_size=3)),
    max_size=4,
)


@st.composite
def manifests(draw):
    manifest = dict(draw(_extra))
    for section in draw(st.lists(st.sampled_from(SECTIONS), unique=True, max_size=4)):
        manifest[section] = draw(_section)
    if draw(st.booleans()):
        manifest["engines"] = {"node": draw(_specs), "npm": draw(st.sampled_from([">=1", "^6"]))}
    keys = list(manifest)
    return {k: manifest[k] for k in draw(st.permutations(keys))}


@given(manifests(), st.sampled_from([None, 0, 2, 4, "\t"]))
def test_fix_manifest_properties(manifest, indent):
    check_manifest(manifest, indent)
