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

### Generate in-game .build files

PoE2 patch 0.5 added a native Build Planner that reads `.build` JSON files
from `Documents/My Games/Path of Exile 2/BuildPlanner/`. Format
spec: https://www.pathofexile.com/developer/docs/game

**By default, every PoE2 import also writes a matching `.build`** into your
BuildPlanner directory (named the same as the saved PoB build), so the build
shows up in-game with no extra step. Disable with `--no-buildfile`, or change
the destination with `--buildfile-dir`.

The `.build` mirrors the official Mobalytics "Build Planner Export" schema:

- **Passives** — the full endgame tree (a superset of any single Mobalytics
  variant), as `{ "id": ... }` objects. Node string IDs come from GGG's
  [poe2-skilltree-export](https://github.com/grindinggear/poe2-skilltree-export).
- **Skills** — every gem group with `support_skills`, plus a per-gem
  `level_interval` (see *progression* below). Gem IDs come from your local
  PoB2 install's `Data/Gems.lua`.
- **Inventory** — one entry per slot with `additional_text` (the item's base
  and explicit mods), `level_interval`, and slot position.

**Progression / per-gem level intervals.** Each gem's start level is
`max(tier_level, variant_level)`:

- *tier_level* — the character level at which the gem first becomes usable,
  derived from its `Tier` (= minimum gem level) via PoB's gem-level requirement
  curve. This is precise to within ~1 level of Mobalytics' own export (the
  residual is GGG quest-reward timing, which isn't in any offline data source).
- *variant_level* — the act in which the build first slots the gem, read from
  the build's `ACT 1 … ENDGAME` variant sets (PoE2 act → level breakpoints).

`guide2pob-buildfile` (re)generates `.build` files for an existing Builds
directory. It recurses into subfolders (skipping `_backup*` / `_duplicates`)
and de-dupes by build name.

```sh
# Regenerate .build files for every build in the auto-detected PoB2 Builds dir
guide2pob-buildfile

# Preview without writing
guide2pob-buildfile --dry-run

# Custom source / destination
guide2pob-buildfile "C:\path\to\Builds" -o "C:\path\to\BuildPlanner"
```

### Customize a loot filter for a build

`guide2pob-filter` turns a NeverSink/FilterBlade base filter into a
build-tailored one. It installs the base filters from a zip (backing up any
existing `*.filter` to `_old_filters_<date>/` first), reads the build's
class/ascendancy/skills from its PoB2 XML to pick an archetype, and injects a
highlight block into NeverSink's OVERRIDE AREA (first-match-wins, so build gear
is loud regardless of strictness). The base filter is never edited in place.

```sh
# Install a base zip and customize the Strict filter for a build
guide2pob-filter --zip "0.5 witch campaign.zip" --build "ED Contagion" --strictness 3

# Reuse already-installed base filters (no zip)
guide2pob-filter --build "ED Contagion"

# No PoB build — classify manually
guide2pob-filter --zip base.zip --name "My Build" --archetype caster
```

Archetypes (`caster`, `minion`, `attack_armour`, `attack_bow`, `crossbow`) are
auto-detected from class/ascendancy and upgraded to `minion` when the build's
skills look summoner-y; override with `--archetype`. Output is written as
`<build name> [<strictness>].filter` into the PoE2 filter folder.

### Sync an existing PoB Builds folder

`guide2pob-sync` walks a Path of Building Builds directory, re-scrapes every
XML that contains a guide URL in its `<Notes>` block, and rewrites the ones
that substantively changed (ignoring PoB runtime state like `PlayerStat`
and `Buffs`). Originals are copied into `_backup_YYYYMMDD/` first.

```sh
# Refresh every build in the auto-detected PoB2 Builds dir
guide2pob-sync

# Or point at a specific directory and preview without writing
guide2pob-sync "C:\path\to\Path of Building (PoE2)\Builds" --dry-run

# Audit against a specific patch tag (default 0.5)
guide2pob-sync --target-patch 0.5
```

The report shows class/ascendancy, the patch number parsed from the title
or notes, and flags any builds tagged for a different patch.


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
