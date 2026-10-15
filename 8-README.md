# Bowerbird

A tiny app store for your Mac, in the terminal. Bowerbird collects apps the way its namesake collects treasures for its bower: from a simple catalog, into one tidy folder.

Fullscreen color-block UI, pure Python 3 standard library, no pip install.

## How it works

- At launch Bowerbird asks for **administrator once**, through the normal macOS password dialog (the same one installers use). It uses that single approval to create `/Applications/Bowerbird` and hand the folder to your user account. Everything after that - installing, updating, running, removing apps - needs no password.
- **If you decline the dialog, Bowerbird tells you so and exits.** No half-installed state, no confusing failure.
- Apps live in `/Applications/Bowerbird/<name>/`. What is installed and which version is tracked in `~/Library/Application Support/bowerbird/installed.json`.

## Run

```
python3 bowerbird.py
```

**Enter** installs the selected app (or runs it if already installed), **X** removes it, **Q** quits. Running an app steps out of the fullscreen UI, shows its output, and waits for you before returning.

## The catalog

`catalog.json` lists what the store offers. Each app is a `.tar.gz` with a run script inside, plus a SHA-256 checksum that Bowerbird verifies before installing anything:

```json
{"apps": [
  {"name": "hello-mac", "version": "1.0.0",
   "description": "says hello from your Mac",
   "url": "apps/hello-mac.tar.gz",
   "sha256": "...", "run": "run.sh"}
]}
```

URLs can be `https://...` or relative paths bundled next to the catalog (two sample apps ship this way). Archives that try to write outside their own folder are refused.

## Honest testing note

None of the development machines are Macs. Bowerbird's logic (admin prompt handling, checksum verification, safe extraction, install/run/remove, state tracking) is covered by unit tests, and the full UI flow - including declining the admin dialog - is exercised in a pseudo-terminal through the offline demo mode (`BOWERBIRD_DEMO=1 python3 bowerbird.py`). It has **not** been run on a real Mac yet; the first real launch is the first real test.

## Development

```
python3 test_core.py   # 10 unit tests: probe, catalog, install, checksums, traversal, state
python3 test_pty.py    # event-driven pseudo-terminal test, demo mode incl. admin denial
```

## License

MIT - see LICENSE.
