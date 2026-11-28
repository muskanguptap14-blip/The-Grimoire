# sample-legacy-3: Ember Ledger

An original Node.js sample written for Grimoire. It is not copied from any real project.

## Original project

`index.js` prints a status line. `package.json` declares dependencies from the early npm era.

## Intentional failures

| Problem | Where | Effect |
|---|---|---|
| `engines.node` is `0.10.x` | `package.json` | excludes every supported Node.js release |
| `jade`, `node-uuid`, `coffee-script` (renamed packages) | `package.json` | the old names are no longer maintained |
| `lodash@^3.10.1`, `fsevents@^1.2.13` | `package.json` | ranges cannot reach a fixed release |

## Expected recovery outcome

With Node support on (`--node`, or the dashboard "Node support" toggle), Grimoire sets `engines.node` to `>=18`, aliases the renamed packages (`npm:pug`, `npm:uuid`, `npm:coffeescript`) and raises the bad ranges. Only `package.json` changes. Grimoire does not run npm or Node, so the proof step is UNVERIFIED for this sample; run `node index.js` yourself to see `EMBER LEDGER ALIVE`.

## Commands

    python -m grimoire autopsy samples/sample-legacy-3 --node
    python -m grimoire revive samples/sample-legacy-3 --node --output /tmp/out3
