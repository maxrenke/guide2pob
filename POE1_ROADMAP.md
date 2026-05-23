# PoE1 Mobalytics Import - Implementation Roadmap

## Overview

This document captures everything needed to extend moba2pob to support
Path of Exile 1 (PoE1) Mobalytics guides. PoE2 support was built first;
PoE1 is a parallel path that reuses the scraper layer unchanged and needs
a new XML emitter, class table, and slot map.

## URL Structure

PoE2: `https://mobalytics.gg/poe2/builds/<slug>`
PoE1: `https://mobalytics.gg/poe/builds/<slug>`

`scrape.fetch_html` only checks for `mobalytics.gg` in the URL, so it
already accepts PoE1 URLs. No change needed there.

`scrape.slug_from_url` uses `/builds/([A-Za-z0-9-]+)` which works for
both paths. No change needed.

## Scraper Assumptions (verify with a real PoE1 page)

The PoE2 scraper relies on:
- `window.__PRELOADED_STATE__` embedded in page HTML
- `userGeneratedDocumentBySlug` key in the state tree
- `buildVariants.values` list of variant dicts
- Variant fields: `passiveTree`, `equipment`, `skillGems`

**Must verify** that Mobalytics PoE1 pages embed the same structure.
Fetch a real PoE1 page and check `_find_build_document()` finds
`buildVariants`. If the key or document structure differs, update
`scrape._find_build_document()`.

Also verify `scrape.variant_labels()` - it looks for `data-key="<id>"`
in the HTML, which should be identical regardless of game version.

## PoB XML Differences (PoE1 vs PoE2)

| Element | PoE2 | PoE1 |
|---------|------|------|
| Root element | `<PathOfBuilding2>` | `<PathOfBuilding>` |
| Build targetVersion | `targetVersion="0_1"` | omit |
| Passive tree lookup | `poe2data.CLASSES` | new `poe1data.CLASSES` |
| PoB install path | `Path of Building Community (PoE2)` | `Path of Building Community` |
| TreeData key | `0_4` (PoE2 tree) | e.g. `3_25` (PoE1 tree) |

The encoding step (`zlib.compress + base64`) is identical for both games.

## New File: `moba2pob/poe1data.py`

Mirror of `poe2data.py` with PoE1 class/ascendancy IDs.
Extracted from PoB Community (PoE1) `Data/Classes.lua`.

PoE1 classes and ascendancies (classId is 1-indexed in PoB tree.lua):

```python
CLASSES = {
    'Witch': {
        'classId': 0, 'integerId': 0,
        'ascendancies': [
            {'name': 'Necromancer', 'internalId': 'Witch1'},
            {'name': 'Occultist',   'internalId': 'Witch2'},
            {'name': 'Elementalist','internalId': 'Witch3'},
        ],
    },
    'Shadow': {
        'classId': 1, 'integerId': 1,
        'ascendancies': [
            {'name': 'Assassin',   'internalId': 'Shadow1'},
            {'name': 'Saboteur',   'internalId': 'Shadow2'},
            {'name': 'Trickster',  'internalId': 'Shadow3'},
        ],
    },
    'Ranger': {
        'classId': 2, 'integerId': 2,
        'ascendancies': [
            {'name': 'Deadeye',    'internalId': 'Ranger1'},
            {'name': 'Raider',     'internalId': 'Ranger2'},
            {'name': 'Pathfinder', 'internalId': 'Ranger3'},
        ],
    },
    'Duelist': {
        'classId': 3, 'integerId': 3,
        'ascendancies': [
            {'name': 'Slayer',     'internalId': 'Duelist1'},
            {'name': 'Gladiator',  'internalId': 'Duelist2'},
            {'name': 'Champion',   'internalId': 'Duelist3'},
        ],
    },
    'Marauder': {
        'classId': 4, 'integerId': 4,
        'ascendancies': [
            {'name': 'Juggernaut', 'internalId': 'Marauder1'},
            {'name': 'Berserker',  'internalId': 'Marauder2'},
            {'name': 'Chieftain',  'internalId': 'Marauder3'},
        ],
    },
    'Templar': {
        'classId': 5, 'integerId': 5,
        'ascendancies': [
            {'name': 'Inquisitor', 'internalId': 'Templar1'},
            {'name': 'Hierophant', 'internalId': 'Templar2'},
            {'name': 'Guardian',   'internalId': 'Templar3'},
        ],
    },
    'Scion': {
        'classId': 6, 'integerId': 6,
        'ascendancies': [
            {'name': 'Ascendant',  'internalId': 'Scion1'},
        ],
    },
}
```

**Verify these IDs** against PoB Community (PoE1) source before shipping.
The `classId` and `integerId` values above are best-guess from memory -
open `TreeData/<version>/tree.lua` and match the `classId` fields there.

## Equipment Slot Differences

PoE1 slot map vs PoE2:

```python
# PoE1 _SLOT_MAP additions/changes vs PoE2:
# - Flask 1-5 (PoE2 has Flask 1-2 only)
# - No Charm 1-3
# - Add 'quiver' -> 'Quiver' (off-hand for bow builds)
# - 'offHand' -> 'Weapon 2' OR 'Offhand' depending on Mobalytics field name
_SLOT_MAP_POE1 = {
    'mainHand': 'Weapon 1', 'offHand': 'Weapon 2', 'helmet': 'Helmet',
    'body': 'Body Armour', 'gloves': 'Gloves', 'boots': 'Boots',
    'amulet': 'Amulet', 'leftRing': 'Ring 1', 'rightRing': 'Ring 2',
    'belt': 'Belt',
    'flask1': 'Flask 1', 'flask2': 'Flask 2', 'flask3': 'Flask 3',
    'flask4': 'Flask 4', 'flask5': 'Flask 5',
}
```

Verify exact Mobalytics field names by inspecting a real PoE1 page's
`buildVariants` JSON (look at `variant['equipment']` keys).

## Skill Gem Differences

PoE1 gems are socketed in items - Mobalytics may represent links
differently from PoE2. PoE2 has a flat `skillGems.gems` list with
`activeSkill` + `subSkills`. Check whether PoE1 uses the same structure.

If different, `_skill_groups()` in convert.py needs a PoE1 branch.
The PoB XML skill representation (`<Skill>`, `<Gem>`) is the same for
both PoE versions.

## Jewels

PoE1 jewel base names differ from PoE2:
- Cobalt Jewel, Crimson Jewel, Viridian Jewel, Prismatic Jewel
- Abyss Jewels: Murderous Eye, Searching Eye, Hypnotic Eye, Ghastly Eye
- Cluster Jewels: Small/Medium/Large with various subtypes

Need a `_JEWEL_BASE_NAMES_POE1` dict. Verify Mobalytics PoE1 jewel slug
format from real page data.

## Amulet Anointment

PoE1 anointments use oils, not PoE2 runes. The anoint field structure
on Mobalytics may differ. The `_anointment_line()` function should still
work if the field contains a `description` or `name`.

## Ascendancy Detection

`convert.detect_ascendancy()` calls `pob.ascendancy_of_node(nid)` which
reads from `tree.lua`. This works identically for PoE1 - just point
`PoBData` at a PoE1 install instead.

A new `PoE1PoBData` class (or a `game` parameter on `PoBData.__init__`)
should look in `Path of Building Community` instead of
`Path of Building Community (PoE2)`.

## `pobdata.py` Changes

Add `game='poe2'` parameter to `find_install()` and `PoBData`:

```python
_DEFAULT_PATHS_POE1 = [
    os.path.expandvars(r'%APPDATA%\Path of Building Community'),
    os.path.expandvars(r'%PROGRAMFILES%\Path of Building Community'),
    ...
]
```

## `convert.py` Changes

The cleanest approach is a `game` parameter threaded through the public
API (`convert()`, `convert_merged()`):

1. `_document()` gets `game='poe2'` param:
   - `poe2`: root is `<PathOfBuilding2>`, Build has `targetVersion="0_1"`
   - `poe1`: root is `<PathOfBuilding>`, no `targetVersion`

2. `_resolve()` imports from `poe1data` when `game='poe1'`

3. `_SLOT_MAP` becomes a dict-of-dicts keyed by game, or a parameter
   passed into `_itemset_xml()`

Minimal surface change - callers just pass `game='poe1'` and the XML
emitted is PoB1-compatible.

## `cli.py` Changes

Auto-detect game from URL:

```python
def _detect_game(url):
    if '/poe2/' in url:
        return 'poe2'
    if '/poe/' in url:
        return 'poe1'
    return 'poe2'  # default
```

Add `--game {poe1,poe2}` flag to override auto-detection.

## pob-mcp Integration

Once PoE1 convert is working, add `import_from_mobalytics` to
`pob-mcp` (the PoE1 MCP server). The handler in pob2-mcp already
shells out to `python -m moba2pob <url>` - the pob-mcp version would
do the same once moba2pob handles PoE1 URLs.

The PoB1 XML uses `zlib.deflateSync` (same as PoE2 for pobb.in), so
`upload_build_to_pobbin` in pob-mcp needs no changes.

## Testing Plan

1. Fetch a real PoE1 Mobalytics guide and save as HTML fixture
2. Verify `parse_build()` extracts `buildVariants` correctly
3. Add `test_convert_poe1.py` mirroring `test_convert.py` with PoE1 fixture
4. Key assertions:
   - Root element is `<PathOfBuilding>` not `<PathOfBuilding2>`
   - No `targetVersion` in Build attributes
   - Class IDs match PoE1 pob.gg tree
   - Flask slots 1-5 present (not Flask 1-2 + Charm 1-3)
5. Manual verify: import generated code into PoB Community (PoE1)
   and check tree renders correctly

## Open Questions

- Does Mobalytics PoE1 use `__PRELOADED_STATE__` or a different embed?
- What are the exact Mobalytics field names for PoE1 equipment slots?
- Does PoE1 use the same `skillGems.gems` structure as PoE2?
- Do PoE1 pages include `attributeNodes` for str/dex/int picks?
- Exact PoE1 jewel slug format from real page data?
- Does pobb.in accept PoE1 codes via the same `/pob/` endpoint?
  (It does serve PoE1 builds - the format difference is in the XML root)
