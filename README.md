# moba2pob

[![CI](https://github.com/maxrenke/moba2pob/actions/workflows/ci.yml/badge.svg)](https://github.com/maxrenke/moba2pob/actions/workflows/ci.yml)

Convert [Mobalytics](https://mobalytics.gg/poe-2) Path of Exile 2 build guides
into [Path of Building](https://pathofbuilding.community/) import codes.

Many Mobalytics PoE2 build guides have **no PoB export** - the author never
attached one. moba2pob scrapes the guide's structured build data (passive
tree, skill gems, equipment) straight from the page and **reconstructs a PoB
import code** from it.

## Features

- **Scrape** any public Mobalytics PoE2 build URL - no login, no browser
  automation, no API key. The build data is embedded in the page.
- **Convert** every build variant into a Path of Building 2 import code.
- **Auto-detect** class and ascendancy from the allocated passive nodes.
- **Path of Building integration** (optional) - uses a local PoB2 install for
  accurate gem names, unique item base types, and the current tree version.
- **LLM analysis** (optional) - get a written build review from Claude
  (Anthropic API) or a local model via Ollama.
- Pure Python 3.9+ standard library. No dependencies.

## Install

```sh
git clone https://github.com/maxrenke/moba2pob
cd moba2pob
pip install -e .          # provides the `moba2pob` command
```

Or run it without installing:

```sh
python -m moba2pob <url>
```

## Usage

```sh
# Convert the first variant, print the PoB code to stdout
moba2pob https://mobalytics.gg/poe-2/builds/ronarray-minion-lich

# Convert every variant into ./out/ as separate builds
moba2pob <url> --variant all -o out/ --xml

# Convert one variant to a file
moba2pob <url> --variant 1 -o build.txt

# Merge all variants into ONE build with switchable Tree/Item/Skill sets
moba2pob <url> --merge -o build.txt

# Upload to pobb.in and print a shareable link (opens directly in PoB)
moba2pob <url> --merge --upload
```

Paste the resulting code into Path of Building 2:
**Import/Export build -> Import from Code**.

### Options

| Flag | Description |
|------|-------------|
| `--variant N` / `--variant all` | Which build variant to convert (default: `0`). |
| `--merge` | Merge all variants into one build with switchable Tree specs, Item Sets, and Skill Sets. |
| `-o, --out PATH` | Output file (single) or directory (`all`). Default: stdout. |
| `--xml` | Also write the raw build XML. |
| `--upload` | Upload to [pobb.in](https://pobb.in) and print both a web link and a `pob2://` link that opens directly in Path of Building 2. |
| `--open` | After `--upload`, launch the `pob2://` link to open the build in PoB2. |
| `-p, --print-code` | Print the import code to stdout even when `-o` is set. |
| `--json` | Dump the scraped build data as JSON and exit. |
| `--class NAME` | Override the detected class. |
| `--ascendancy NAME` | Override the detected ascendancy. |
| `--level N` | Character level to record (default: 90). |
| `--pob-path DIR` | Path of Building (PoE2) install directory. |
| `--no-pob` | Ignore any Path of Building install. |
| `--analyze` | Run an LLM analysis of the build. |
| `--provider` | `anthropic` (default), `ollama`, or `none`. |
| `--model` / `--api-key` / `--ollama-url` | LLM configuration. |

### Path of Building integration

If a *Path of Building Community (PoE2)* install is found, moba2pob reads its
data files for accurate results. Detection order:

1. `--pob-path`
2. `POB2_PATH` environment variable
3. Common install locations.

Without an install, conversion still works but gem names are approximate and
you must pass `--ascendancy` so the class can be resolved.

### LLM analysis

```sh
# Claude (Anthropic API)
export ANTHROPIC_API_KEY=sk-ant-...
moba2pob <url> --analyze --provider anthropic

# Local model via Ollama
moba2pob <url> --analyze --provider ollama --model qwen2.5-coder:14b
```

The analysis is informational - it never changes the generated code.

## How it works

1. Mobalytics is a Next.js app that embeds the full build in a
   `window.__PRELOADED_STATE__` blob in the page HTML.
2. moba2pob extracts that blob and locates the build document.
3. Each variant's passive tree, skill gems, and equipment are translated into
   Path of Building XML. Mobalytics passive node slugs (`node-62677`) use the
   same numeric IDs as PoB's passive tree, so the tree maps across directly.
4. The XML is zlib-deflated and base64-encoded into a PoB import code.

## Accuracy and limitations

- **Passive tree** maps 1:1 and is reliable.
- **Gem names** come from Path of Building's own data when available; a gem
  shown red in PoB just needs a name touch-up.
- **Items** are reconstructed from Mobalytics mod text. Rare items use their
  base type as the name; uniques resolve their base type from PoB data.
- Attribute passive choices (str/dex/int) and a build's second weapon set are
  not yet encoded.
- Mobalytics may change its page structure; if scraping breaks, open an issue.

This is an unofficial tool. Path of Exile and Path of Building are the
property of their respective owners.

## Development

```sh
git clone https://github.com/maxrenke/moba2pob
cd moba2pob
pip install -e .
python -m unittest discover -v
```

CI runs the test suite on Python 3.9-3.13 on Ubuntu and Windows.

## License

MIT - see [LICENSE](LICENSE).
