# sample-legacy-2: Lost Ledger

An original sample written for Grimoire. It imitates a ledger helper from the Python 2 era. It is not copied from any real project.

## Original project

`main.py` reads ledger settings from an INI string, queues entries and prints a status line. At runtime it needs only the standard library plus `six`. `urllib2` is imported only for its exception class; no network call is made.

## Intentional failures

| Problem | Where | Effect |
|---|---|---|
| `ConfigParser`, `Queue`, `urllib2`, `StringIO` imports | `main.py` | `ModuleNotFoundError` on Python 3.11 |
| `beautifulsoup` (renamed to `beautifulsoup4`) | `requirements.txt` line 1 | cannot be installed |
| `distribute`, `ordereddict` (removed packages) | `requirements.txt` lines 2-3 | cannot be installed |
| `beautifulsoup4` declared again after the rename | `requirements.txt` line 4 | duplicate requirement |
| `six` imported but not declared | `main.py` | missing dependency |

Before revival, `python main.py` exits non-zero.

## Expected recovery outcome

Grimoire rewrites the four imports, renames and de-duplicates `beautifulsoup`, drops `distribute` and `ordereddict`, and adds `six`. The recovered `requirements.txt` is `beautifulsoup4` and `six`. With a local wheelhouse containing those two packages, `prove` installs them with `pip --no-index`, runs `main.py`, and prints `LOST LEDGER ALIVE`. Without a wheelhouse, `prove` reports UNVERIFIED because the dependencies cannot be installed offline.

## Commands

    python -m grimoire autopsy samples/sample-legacy-2
    python -m grimoire revive samples/sample-legacy-2 --output /tmp/out2
    python -m grimoire prove samples/sample-legacy-2 --wheelhouse DIR
