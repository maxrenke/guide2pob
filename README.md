# guide2pob

[![CI](https://github.com/maxrenke/guide2pob/actions/workflows/ci.yml/badge.svg)](https://github.com/maxrenke/guide2pob/actions/workflows/ci.yml)

Convert [Mobalytics](https://mobalytics.gg/poe-2) and [Maxroll](https://maxroll.gg/poe2)
Path of Exile build guides into [Path of Building](https://pathofbuilding.community/) import codes.

Build guides rarely ship with a PoB export. guide2pob scrapes the guide's structured build data
(passive tree, skill gems, equipment) straight from the page and **reconstructs a PoB import code**
from it.

## Features

- **Mobalytics** (PoE1 + PoE2) and **Maxroll** (PoE2) build guide support.
- **Scrape** any public guide URL - no login, no browser automation, no API key.
- **Convert** every build variant / phase into a Path of Building import code.
- **Auto-detect** class and ascendancy from the allocated passive nodes.
- **Merge** all variants into one build with switchable Tree specs, Item Sets, and Skill Sets.
- **Guide text** injected into PoB Notes so the full write-up travels with the build.
- **Path of Building integration** (optional) - uses a local PoB2 install for accurate gem names,
  unique item base types, and the current tree version.
- Pure Python 3.9+ standard library. No dependencies.

## Install

```sh
git clone https://github.com/maxrenke/guide2pob
cd guide2pob
pip install -e .          # provides the `guide2pob` command
```

Or run it without installing:

```sh
python -m guide2pob <url>
```

## Usage

```sh
# Convert a Mobalytics build (all variants merged, default)
guide2pob https://mobalytics.gg/poe-2/builds/ronarray-minion-lich

# Convert a Maxroll build guide
guide2pob https://maxroll.gg/poe2/build-guides/disciple-of-varashta-plant-build-guide

# Convert a specific variant/phase by index
guide2pob <url> --variant 1 -o build.txt

# Convert every variant into ./out/ as separate builds
guide2pob <url> --variant all -o out/ --xml

# Upload to pobb.in and print a shareable link (opens directly in PoB)
guide2pob <url> --merge --upload
```

Paste the resulting code into Path of Building 2:
**Import/Export build -> Import from Code**.

### Options

| Flag | Description |
|------|-------------|
| `--variant N` / `--variant all` | Which build variant/phase to convert (default: last/all merged). |
| `--merge` | Merge all variants into one build with switchable Tree specs, Item Sets, and Skill Sets (default: on). |
| `-o, --out PATH` | Output file (single) or directory (`all`). Default: ~/Downloads. |
| `--xml` | Also write the raw build XML. |
| `--upload` | Upload to [pobb.in](https://pobb.in) and print both a web link and a `pob2://` link. |
| `--open` | After saving, launch Path of Building (default: on). |
| `-p, --print-code` | Print the import code to stdout even when `-o` is set. |
| `--info` | Print build name, variants, and class without converting. |
| `--json` | Dump the scraped build data as JSON and exit. |
| `--class NAME` | Override the detected class. |
| `--ascendancy NAME` | Override the detected ascendancy. |
| `--level N` | Character level to record (default: 90). |
| `--pob-path DIR` | Path of Building (PoE2) install directory. |
| `--no-pob` | Ignore any Path of Building install. |

### Path of Building integration

If a *Path of Building Community (PoE2)* install is found, guide2pob reads its
data files for accurate results. Detection order:

1. `--pob-path`
2. `POB2_PATH` environment variable
3. Common install locations.

Without an install, conversion still works but gem names are approximate and
you must pass `--ascendancy` so the class can be resolved.

## How it works

**Mobalytics** is a Next.js app that embeds the full build in a `window.__PRELOADED_STATE__`
blob in the page HTML. guide2pob extracts that blob and locates the build document.

**Maxroll** uses a Remix framework; build guide pages embed a planner link
(`/poe2/planner/<id>`), and the planner page contains the full structured build state in
`window.__remixContext`. guide2pob fetches both pages automatically from a guide URL.

In both cases each variant's passive tree, skill gems, and equipment are translated into
Path of Building XML, then zlib-deflated and base64-encoded into a PoB import code.
Passive node IDs are the same numeric values PoB uses, so the tree maps across directly.

## Accuracy and limitations

- **Passive tree** maps 1:1 and is reliable.
- **Gem names** come from Path of Building's own data when available; a gem
  shown red in PoB just needs a name touch-up.
- **Items** are reconstructed from guide data. Unique item base types are resolved
  from PoB data; rare items use a best-effort base type derived from the item metadata.
- Mobalytics may change its page structure; Maxroll similarly. If scraping breaks, open an issue.

This is an unofficial tool. Path of Exile and Path of Building are the
property of their respective owners.

## Development

```sh
git clone https://github.com/maxrenke/guide2pob
cd guide2pob
pip install -e .
python -m pytest
```

CI runs the test suite on Python 3.9-3.13 on Ubuntu and Windows.

## License

MIT - see [LICENSE](LICENSE).
