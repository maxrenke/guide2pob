# Mobalytics / Maxroll Converter Parity Matrix

Status codes: OK=at parity, MOBA-ONLY=Mobalytics has it / Maxroll does not,
MAXROLL-ONLY=Maxroll has it / Mobalytics does not, GAP=both have it but differ,
N/A=feature not applicable (source data unavailable).

| Feature | Mobalytics | Maxroll | Status | Notes |
|---------|-----------|---------|--------|-------|
| Passive tree (main nodes) | OK | OK | OK | |
| Passive tree (ascendancy nodes) | OK | OK | OK | |
| Weapon-set 2 tree nodes | OK | OK | OK | WeaponSet2 XML |
| Attribute overrides (str/dex/int) | OK | hardcoded empty | N/A | Maxroll planner has no attr-override data |
| Jewels in tree sockets | OK | OK | OK | |
| Empty jewel socket (no jewel) | OK | FIXED | OK | #2 done |
| Ascendancy auto-detection | voting on nodes | internal ID lookup | OK | Different methods, both work |
| Items - rare | OK | OK | OK | |
| Items - unique w/ fallback base | OK | FIXED | OK | #3 done - imports _FALLBACK_UNIQUE_BASES |
| Items - magic | not supported | OK | N/A | Mobalytics doesn't expose magic items |
| Item implicits | OK | FIXED | OK | #5 done |
| Item explicits | OK | FIXED | OK | #5 done |
| Item runes / sockets | OK | not in Maxroll data | N/A | Maxroll planner has no rune data |
| Item anointment | OK | not in Maxroll data | N/A | Maxroll planner has no anointment data |
| Weapon swap slot | OK | OK | OK | |
| Base type map (weapons/armor) | N/A | EXPANDED | OK | #3b done - added wands/bows/sceptres/etc |
| Gem name resolution | pob lookup + slug prettify | pob lookup + CamelCase split | OK | Both work |
| Gem level | hardcoded 20 | reads from data | N/A | Mobalytics doesn't expose gem level |
| Gem quality | hardcoded 0 | hardcoded 0 | OK | |
| Single-variant convert | OK | OK | OK | |
| Multi-variant / merged convert | OK | OK | OK | |
| Progression order sort | OK (by node count) | FIXED | OK | #9 done |
| Notes - URL + build name | OK | OK | OK | |
| Notes - og:description | OK | OK | OK | |
| Notes - guide text | OK (lexical blocks) | OK (main-article) | OK | |
| Notes - ascendancy priority list | OK | not in Maxroll data | N/A | Maxroll has no priority list concept |
| Notes - equipment priority list | OK | not in Maxroll data | N/A | |
| Notes - gem priority list | OK | not in Maxroll data | N/A | |
| --info command | OK | OK | OK | |
| --json command | OK | OK | OK | |
| Test coverage | high | FIXED | OK | #11 done - 35 new tests |

## Work log

- [x] #2 Maxroll: empty jewel socket emission fix - fixed dead loop
- [x] #3 Maxroll: unique base fallback dict - imports from convert.py
- [x] #3b Maxroll: base type map expansion - wands, bows, sceptres, shields, axes, maces, swords, claws, daggers, crossbows, flails, spears
- [x] #5 Maxroll: item implicits + explicits - handles string/dict/text/value/description formats
- [x] #9 Maxroll: progression order sort - convert_merged now accepts progression_order param, cli passes no_reorder flag
- [x] #11 Maxroll: test coverage - added tests/test_convert_maxroll.py with 35 tests and sample_maxroll_planner fixture

## Intentional N/A items

- Attribute overrides: Maxroll planner stores raw node IDs with no str/dex/int labeling
- Item runes/soul cores: not present in Maxroll planner data
- Item anointment: not present in Maxroll planner data
- Priority lists (ascendancy/equipment/gem): Maxroll has no equivalent concept
- Magic item rarity: Mobalytics doesn't expose magic items (all non-unique are RARE)
- Gem level in Mobalytics: source data doesn't include gem levels (hardcoded 20 is correct)
