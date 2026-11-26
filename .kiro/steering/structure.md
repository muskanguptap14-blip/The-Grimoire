# Grimoire: Structure

```
The-Grimoire/
├── .kiro/
│   ├── steering/            product.md, tech.md, structure.md, quality.md
│   ├── specs/grimoire-core/ requirements.md, design.md, tasks.md
│   └── hooks/               pytest-on-save
├── src/grimoire/
│   ├── __main__.py, cli.py  CLI entry
│   ├── models.py            Finding, Report, PatchResult, ProofResult (frozen dataclasses)
│   ├── scan.py              file discovery, repo type detection
│   ├── py2parse.py          Python 2 / 3 parsing facade (lib2to3 + ast)
│   ├── autopsy.py           builds the Cause of Death report
│   ├── codemods/            one module per rule (print_stmt, except_as, ...)
│   ├── imports.py           outdated import rewrites
│   ├── requirements.py      requirements.txt parser and fixer
│   ├── nodejs.py            stretch: package.json modernizer
│   ├── diffing.py           Resurrection Diff
│   ├── dockerfile.py        Dockerfile text generator
│   ├── verify.py            temp venv and subprocess runner
│   ├── data/                imports_map.json, packages_map.json, node_map.json
│   └── dashboard/           server.py, static/ (index.html, app.css, app.js)
├── samples/
│   ├── crypt_calculator/    original dead Python 2 mini-repo
│   └── lost_ledger/         original dead mini-repo with bad requirements and old imports
├── tests/
│   ├── unit/, property/, integration/
│   └── conftest.py
├── pyproject.toml
└── README.md
```

## Conventions
- One codemod per file in `codemods/`. Each exposes `RULE_ID`, `apply(tree) -> tree`, and registers in `codemods/__init__.py` in a fixed order.
- Pure functions in the engine. File and process I/O stays in `scan.py`, `verify.py` and the CLI.
- Data tables are JSON, loaded once, and validated by a test (no duplicate keys, all targets non-empty).
- Test files mirror source names: `src/grimoire/imports.py` -> `tests/unit/test_imports.py`.
- Samples are test fixtures. Tests copy them to a temp dir and never edit them in place.
