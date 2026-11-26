# sample-legacy-1: Tally Keeper

An original sample written for Grimoire. It imitates a small shop-counter ledger script from the Python 2.5 era. It is not copied from any real project.

## Original project

`main.py` builds a table of sales, totals the units and prints a banner. It has no third-party dependencies and no `requirements.txt`.

## Intentional failures (Python 2 only constructs)

| Construct | Where | Effect on Python 3.11 |
|---|---|---|
| `print` statements | `main`, `parse_quantity` | `SyntaxError` |
| `except ValueError, e` | `parse_quantity` | `SyntaxError` |
| `0755` octal literal | `report_mode` | `SyntaxError` |
| `<>` operator | `main` | `SyntaxError` |
| `raw_input`, `xrange` | `ask`, `load_sales` | `NameError` at call time |
| `dict.has_key`, `dict.iteritems` | `total` | `AttributeError` at call time |

Before revival, `python main.py` exits non-zero.

## Expected recovery outcome

Grimoire rewrites the syntax and builtins, reports no remaining findings, and the entry point `main.py` prints `TALLY KEEPER ALIVE` and exits 0.

## Commands

    python -m grimoire autopsy samples/sample-legacy-1
    python -m grimoire revive samples/sample-legacy-1 --output /tmp/out1
    python -m grimoire prove samples/sample-legacy-1
