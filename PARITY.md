# Mobalytics / Maxroll Converter Parity Matrix

Status codes: OK=at parity, MOBA-ONLY=Mobalytics has it / Maxroll does not,
MAXROLL-ONLY=Maxroll has it / Mobalytics does not, GAP=both have it but differ,
N/A=feature not applicable (source data unavailable).

| Feature | Mobalytics | Maxroll | Status | Notes |
|---------|-----------|---------|--------|-------|
| Passive tree (main nodes) | OK | OK | OK | |
| Passive tree (ascendancy nodes) | OK | OK | OK | |
| Weapon-set 2 tree nodes | OK | OK | OK | WeaponSet2 XML |
| Attribute overrides (str/dex/int) | OK | OK | OK | Both emit AttributeOverride XML; Maxroll requires PoB install |
| Jewels in tree sockets | OK | OK | OK | |
| Empty jewel socket (no jewel) | OK | OK | OK | |
| Ascendancy auto-detection | voting on nodes | internal ID lookup | OK | Different methods, both work |
| Items - rare | OK | OK | OK | |
| Items - unique w/ fallback base | OK | OK | OK | |
| Items - magic | not supported | OK | N/A | Mobalytics doesn't expose magic items |
| Item level | hardcoded 82 | reads from data | MAXROLL-ONLY | Mobalytics source data has no ilvl |
| Item implicits | text strings | mod ID + value lookup | OK | Maxroll uses PoB2 ModItem.lua for exact text |
| Item explicits | text strings | mod ID + value lookup | OK | |
| Item enchants / anointments | before Implicits: header | before Implicits: header | OK | Both place enchants before Implicits: N line |
| Item runes / sockets | name-only (Rune: X) | stat values from stats.rune | GAP | Mobalytics has no rune values; Maxroll exports net stat effect |
| Weapon swap slot | OK | OK | OK | |
| Base type map (weapons/armor/jewels) | N/A | OK | OK | Full _BASE_MAP in convert_maxroll.py |
| Gem name resolution | pob lookup + slug prettify | pob lookup + CamelCase split | OK | Both work |
| Gem level | hardcoded 20 | reads from data | MAXROLL-ONLY | Mobalytics source data has no gem level |
| Gem quality | hardcoded 0 | reads from data | MAXROLL-ONLY | Mobalytics source data has no gem quality |
| Single-variant convert | OK | OK | OK | |
| Multi-variant / merged convert | OK | OK | OK | |
| Progression order sort | OK (by node count) | OK (by node count) | OK | |
| Notes - URL + build name | OK | OK | OK | |
| Notes - og:description | OK | OK | OK | |
| Notes - guide text | OK (lexical blocks) | OK (main-article div) | OK | |
| Notes - ascendancy priority list | OK | not in Maxroll data | MOBA-ONLY | Maxroll has no priority list concept |
| Notes - equipment priority list | OK | not in Maxroll data | MOBA-ONLY | |
| Notes - gem priority list | OK | not in Maxroll data | MOBA-ONLY | |
| Scraper layout compat | single format | old (planner key) + new (profiles[]) | OK | Both Maxroll layouts supported |
| --info command | OK | OK | OK | |
| --json command | OK | OK | OK | |
| Test coverage | high | high | OK | 182 tests total |

## Work log

### Session 1 (prior)
- [x] #2 Maxroll: empty jewel socket emission fix
- [x] #3 Maxroll: unique base fallback dict
- [x] #3b Maxroll: base type map expansion
- [x] #5 Maxroll: item implicits + explicits (old format)
- [x] #9 Maxroll: progression order sort
- [x] #11 Maxroll: test coverage (35 new tests)

### Session 2 (2026-05-25)
- [x] Maxroll scraper: new profiles[] layout support (2026 Maxroll update)
- [x] Maxroll items: rewrote _item_text to use mods dict + PoB2 mod_texts lookup
- [x] Maxroll items: real ilvl from item data
- [x] Maxroll items: rune/soul-core stats via _RUNE_STAT_TEXT (net stat effect)
- [x] Maxroll items: enchant mods placed before Implicits: N (anointment-correct)
- [x] Maxroll gems: real gem level + quality from data
- [x] Maxroll attribute overrides: implemented via PoBData.attribute_options
- [x] PoBData: added attribute_options property (parses tree.lua isAttribute nodes)
- [x] PoBData: added mod_texts property (parses ModItem.lua + 5 other Mod*.lua files)
- [x] Tests: updated fixtures to new item format; added _FakePobMods; 182 tests passing
- [x] Charm base type: fixed fourcharm -> Silver Charm (was Quicksilver Flask, a PoE1 item)

## Intentional N/A / structural gaps

- Priority lists (ascendancy/equipment/gem): Maxroll has no equivalent concept in planner data
- Magic item rarity: Mobalytics doesn't expose magic items (all non-unique are RARE)
- Gem level/quality in Mobalytics: source data doesn't include these values
- Item level in Mobalytics: source data doesn't include ilvl (hardcoded 82)
- Rune stat values in Mobalytics: source provides rune names only; PoB cannot compute rune effects
- Attribute overrides without PoB install: requires tree.lua parsing; emits empty lists gracefully
- Unique display names without PoB install: falls back to base type name; stats still export correctly
