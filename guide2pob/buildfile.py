"""Generate Path of Exile 2 in-game .build files from PoB build XML.

The .build format is the JSON document PoE2's Build Planner reads from
``Documents/My Games/Path of Exile 2/BuildPlanner/``. Schema:
https://www.pathofexile.com/developer/docs/game

Passive nodes are referenced by their PassiveSkills table string id
(e.g. ``strength89``), not the numeric ids PoB stores. The mapping is
sourced from the GGG-published export at
https://github.com/grindinggear/poe2-skilltree-export which carries both
``skill`` (numeric, PoB-side) and ``id`` (string, .build-side) on every node.
"""
import os
import re
import json
import urllib.request
import xml.etree.ElementTree as ET

from .poe2data import CLASSES

# Default cache for the GGG skill-tree export.
TREE_EXPORT_URL = ('https://raw.githubusercontent.com/grindinggear/'
                   'poe2-skilltree-export/main/data.json')

# PoB slot name -> .build inventory_id, in the emission order Mobalytics uses.
# Note the weapon mapping: PoB's main set is Weapon 1 (main hand) + Weapon 2
# (off hand / focus / shield); the weapon-swap set's main hand is "Weapon 1
# Swap". The .build schema names these Weapon1 / Offhand1 / Weapon2 / Offhand2.
SLOT_INVENTORY_ID = [
    ('Weapon 1',      'Weapon1'),
    ('Weapon 1 Swap', 'Weapon2'),
    ('Weapon 2',      'Offhand1'),
    ('Weapon 2 Swap', 'Offhand2'),
    ('Helmet',        'Helm'),
    ('Body Armour',   'BodyArmour'),
    ('Gloves',        'Gloves'),
    ('Boots',         'Boots'),
    ('Amulet',        'Amulet'),
    ('Belt',          'Belt'),
    ('Ring 1',        'Ring'),
    ('Ring 2',        'Ring2'),
    ('Flask 1',       'Flask1'),
    ('Flask 2',       'Flask2'),
    ('Flask 3',       'Flask3'),
    ('Flask 4',       'Flask4'),
    ('Flask 5',       'Flask5'),
    ('Charm 1',       'Charm1'),
    ('Charm 2',       'Charm2'),
    ('Charm 3',       'Charm3'),
]


# -- skill tree mapping cache ----------------------------------------------

def _default_cache_dir():
    return os.path.join(os.path.expanduser('~'), '.cache', 'guide2pob')


def load_tree_export(path=None, refresh=False):
    """Return the GGG skill-tree export, downloading on first use."""
    p = path or os.path.join(_default_cache_dir(), 'poe2-skilltree.json')
    if refresh or not os.path.isfile(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        req = urllib.request.Request(
            TREE_EXPORT_URL, headers={'User-Agent': 'guide2pob'})
        data = urllib.request.urlopen(req, timeout=30).read()
        with open(p, 'wb') as f:
            f.write(data)
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def build_node_id_map(tree_export):
    """Return {numeric_skill_id_str: passive_skill_string_id}."""
    out = {}
    for v in (tree_export.get('nodes') or {}).values():
        if isinstance(v, dict) and v.get('skill') is not None and v.get('id'):
            out[str(v['skill'])] = v['id']
    return out


# -- gem name -> Metadata path ---------------------------------------------

_GEM_NAME_TO_ID_CACHE = {}


def _gem_name_to_id(pob):
    """Return {lowercased gem name: 'Metadata/Items/Gems/...'} from PoB data."""
    if not pob:
        return {}
    key = getattr(pob, "path", None) or id(pob)
    cached = _GEM_NAME_TO_ID_CACHE.get(key)
    if cached is not None:
        return cached
    m = {}
    f = os.path.join(pob.path, 'Data', 'Gems.lua')
    if os.path.isfile(f):
        text = open(f, encoding='utf-8').read()
        pat = re.compile(
            r'\["(Metadata/Items/Gems/[^"]+)"\]\s*=\s*\{(.*?)\n\t\}', re.S)
        for blk in pat.finditer(text):
            nm = re.search(r'name = "([^"]+)"', blk.group(2))
            if nm:
                m[nm.group(1).lower()] = blk.group(1)
    _GEM_NAME_TO_ID_CACHE[key] = m
    return m


# Gem-level -> character level requirement (PoE2). A gem's Tier equals the
# minimum gem level needed to create it, so a gem's earliest usable character
# level is this curve indexed by its Tier. Used as a fallback when PoB's live
# skill data can't be read. Index 0 == gem level 1.
_GEM_REQ_CURVE_FALLBACK = [1, 3, 6, 10, 14, 18, 22, 26, 31, 36, 41, 46, 52,
                           58, 64, 66, 72, 78, 84, 90]

_GEM_META_CACHE = {}
_GEM_CURVE_CACHE = {}


def _gem_name_to_meta(pob):
    """Return {lowercased gem name: {'id': metadata_path, 'tier': int}}."""
    if not pob:
        return {}
    key = getattr(pob, "path", None) or id(pob)
    cached = _GEM_META_CACHE.get(key)
    if cached is not None:
        return cached
    out = {}
    f = os.path.join(pob.path, 'Data', 'Gems.lua')
    if os.path.isfile(f):
        text = open(f, encoding='utf-8').read()
        pat = re.compile(
            r'\["(Metadata/Items/Gems/[^"]+)"\]\s*=\s*\{(.*?)\n\t\}', re.S)
        for blk in pat.finditer(text):
            body = blk.group(2)
            nm = re.search(r'name = "([^"]+)"', body)
            if not nm:
                continue
            tier_m = re.search(r'Tier = (\d+)', body)
            out[nm.group(1).lower()] = {
                'id': blk.group(1),
                'tier': int(tier_m.group(1)) if tier_m else 0,
            }
    _GEM_META_CACHE[key] = out
    return out


def _gem_req_curve(pob):
    """Return the gem-level -> character-level requirement curve (index 0 ==
    gem level 1), read from PoB skill data with a baked-in fallback."""
    if not pob:
        return _GEM_REQ_CURVE_FALLBACK
    key = getattr(pob, "path", None) or id(pob)
    cached = _GEM_CURVE_CACHE.get(key)
    if cached is not None:
        return cached
    curve = None
    skills_dir = os.path.join(pob.path, 'Data', 'Skills')
    if os.path.isdir(skills_dir):
        import glob as _glob
        for f in _glob.glob(os.path.join(skills_dir, '*.lua')):
            try:
                t = open(f, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            i = t.find('["EssenceDrainPlayer"]')
            if i < 0:
                continue
            pairs = re.findall(
                r'\[(\d+)\]\s*=\s*\{[^}]*?levelRequirement\s*=\s*(\d+)',
                t[i:i + 12000], re.S)
            vals = [max(1, int(r)) for _, r in pairs]
            if vals:
                curve = vals
            break
    curve = curve or list(_GEM_REQ_CURVE_FALLBACK)
    _GEM_CURVE_CACHE[key] = curve
    return curve


def tier_to_level(tier, curve):
    """Map a gem Tier to the character level at which it first becomes usable."""
    if not tier or tier < 1:
        return 1
    idx = min(tier - 1, len(curve) - 1)
    return max(1, curve[idx])


# -- PoB XML parsing -------------------------------------------------------

def _largest_index(elements, count_attr_extractor):
    """Return the 0-based index of the element with the largest extracted count."""
    if not elements:
        return None
    best_i, best_n = 0, -1
    for i, el in enumerate(elements):
        n = count_attr_extractor(el)
        if n > best_n:
            best_i, best_n = i, n
    return best_i


def parse_pob_xml(xml_text, *, prefer='largest'):
    """Extract the structured slice of a PoB build XML.

    ``prefer`` selects which Spec/SkillSet/ItemSet to use when there are
    multiple variants:
      - 'largest': the spec with the most passives (= endgame target).
      - 'active':  whichever the build's active{Spec,SkillSet,ItemSet}
                   attributes point at.
    """
    root = ET.fromstring(xml_text)
    build = root.find('Build')
    cls_name = build.get('className', '') if build is not None else ''
    asc_name = build.get('ascendClassName', '') if build is not None else ''
    level = int((build.get('level') if build is not None else '90') or '90')

    tree_el = root.find('Tree')
    specs = list(tree_el.findall('Spec')) if tree_el is not None else []
    skills_el = root.find('Skills')
    skillsets = list(skills_el.findall('SkillSet')) if skills_el is not None else []
    items_el = root.find('Items')
    itemsets = list(items_el.findall('ItemSet')) if items_el is not None else []

    if prefer == 'largest':
        spec_i = _largest_index(specs, lambda s:
            len([n for n in (s.get('nodes', '') or '').split(',') if n]))
        # Skillsets and itemsets typically track specs 1:1 by index. If the
        # paired set is missing or empty, walk backward to the closest set
        # that actually has content (PoB builds sometimes leave the final
        # itemset as a placeholder).
        def _pick(start, sets, count_fn):
            if not sets:
                return None
            i = min(start if start is not None else 0, len(sets) - 1)
            while i >= 0:
                if count_fn(sets[i]) > 0:
                    return i
                i -= 1
            return min(start if start is not None else 0, len(sets) - 1)
        skill_i = _pick(spec_i, skillsets, lambda s: len(s.findall('Skill')))
        item_i = _pick(spec_i, itemsets, lambda s: len(s.findall('Slot')))
    else:
        def _idx(el, attr, lst):
            try:
                return max(0, int((el.get(attr) if el is not None else '1') or '1') - 1)
            except ValueError:
                return 0
        spec_i = _idx(tree_el, 'activeSpec', specs) if specs else None
        skill_i = _idx(skills_el, 'activeSkillSet', skillsets) if skillsets else None
        item_i = _idx(items_el, 'activeItemSet', itemsets) if itemsets else None

    # Passive nodes
    spec = specs[spec_i] if spec_i is not None else None
    node_ids = []
    if spec is not None:
        node_ids = [n for n in (spec.get('nodes', '') or '').split(',') if n.isdigit()]

    # Skill groups
    skill_groups = []
    if skill_i is not None and skill_i < len(skillsets):
        groups = list(skillsets[skill_i].findall('Skill'))
    elif skills_el is not None and not skillsets:
        groups = list(skills_el.findall('Skill'))
    else:
        groups = []
    for grp in groups:
        gems = [g.get('nameSpec', '') for g in grp.findall('Gem')
                if g.get('nameSpec') and g.get('enabled', 'true').lower() == 'true']
        if gems:
            skill_groups.append({'label': grp.get('label', ''), 'gems': gems})

    # Equipment
    slot_map = {}
    if item_i is not None and item_i < len(itemsets):
        for slot in itemsets[item_i].findall('Slot'):
            slot_map[slot.get('name', '')] = slot.get('itemId', '')

    items_by_id = {}
    if items_el is not None:
        for it in items_el.findall('Item'):
            iid = it.get('id', '')
            if iid:
                items_by_id[iid] = (it.text or '').strip()

    notes_el = root.find('Notes')
    notes = (notes_el.text or '').strip() if notes_el is not None else ''

    return {
        'class_name': cls_name,
        'ascend_name': asc_name,
        'level': level,
        'node_ids': node_ids,
        'skill_groups': skill_groups,
        'slot_map': slot_map,
        'items_by_id': items_by_id,
        'notes': notes,
    }


# -- variant progression ----------------------------------------------------

# Approximate character level at the start of each PoE2 campaign act. Used to
# turn a build's act-staged variants into per-gem/-item level intervals.
ACT_START_LEVEL = {1: 1, 2: 12, 3: 22, 4: 33, 5: 40, 6: 50}
_ENDGAME_LEVEL = 65


def variant_start_level(title, index=0, total=1):
    """Map a PoB variant/set title (e.g. 'ACT 2', 'ENDGAME (LOW LIFE)') to the
    approximate character level at which that stage begins."""
    t = (title or '').lower()
    m = re.search(r'act\s*(\d+)', t)
    if m:
        n = int(m.group(1))
        # "Act N - Endgame" style still keys off the act number.
        return ACT_START_LEVEL.get(n, _ENDGAME_LEVEL)
    if 'endgame' in t or 'maps' in t or 'pinnacle' in t:
        return _ENDGAME_LEVEL
    # Unlabelled: spread evenly across 1..endgame by position.
    if total > 1:
        return 1 + round((_ENDGAME_LEVEL - 1) * index / (total - 1))
    return 1


def _sets_in_order(parent, tag):
    return list(parent.findall(tag)) if parent is not None else []


def parse_pob_progression(xml_text):
    """Like parse_pob_xml(prefer='largest') but also derives, by scanning every
    variant set in order, the earliest character level at which each gem and
    each equipped slot first appears. Returns the largest-variant structure plus
    ``gem_levels`` ({gem_name_lower: level}) and ``item_levels`` ({slot: level}).
    """
    base = parse_pob_xml(xml_text, prefer='largest')

    root = ET.fromstring(xml_text)
    skills_el = root.find('Skills')
    items_el = root.find('Items')
    skillsets = _sets_in_order(skills_el, 'SkillSet')
    itemsets = _sets_in_order(items_el, 'ItemSet')

    gem_levels = {}
    for i, ss in enumerate(skillsets):
        lvl = variant_start_level(ss.get('title'), i, len(skillsets))
        for grp in ss.findall('Skill'):
            for g in grp.findall('Gem'):
                nm = g.get('nameSpec')
                if nm and g.get('enabled', 'true').lower() == 'true':
                    key = nm.lower()
                    if key not in gem_levels or lvl < gem_levels[key]:
                        gem_levels[key] = lvl

    item_levels = {}
    for i, iset in enumerate(itemsets):
        lvl = variant_start_level(iset.get('title'), i, len(itemsets))
        for slot in iset.findall('Slot'):
            nm = slot.get('name')
            if nm and slot.get('itemId'):
                if nm not in item_levels or lvl < item_levels[nm]:
                    item_levels[nm] = lvl

    base['gem_levels'] = gem_levels
    base['item_levels'] = item_levels
    return base


# -- assembly --------------------------------------------------------------

def _ascendancy_internal_id(name):
    for cls in CLASSES.values():
        for a in cls['ascendancies']:
            if a['name'].lower() == (name or '').lower():
                return a['internalId']
    return None


def _item_first_line(text, prefix='Rarity:'):
    if not text:
        return None
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s if s.startswith(prefix) else None
    return None


def _item_name_and_unique(text):
    if not text:
        return None, False
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or not lines[0].lower().startswith('rarity:'):
        return None, False
    is_unique = lines[0].split(':', 1)[1].strip().lower() == 'unique'
    name = lines[1].strip() if len(lines) > 1 else None
    return name, is_unique


_ITEM_TRAILERS = ('corrupted', 'mirrored', 'fractured', 'split',
                  'synthesised', 'note:', 'crafted:', 'implicit')


def item_additional_text(text):
    """Render a PoB item as Mobalytics' .build `additional_text`.

    Format: a header line (the unique name for uniques, else the base type)
    followed by numbered explicit mod lines, e.g.::

        Withered Wand
        1. 44% increased Spell Damage
        2. +1 to Level of all Chaos Spell Skills

    Returns None when the text isn't a parseable item.
    """
    if not text:
        return None
    raw = [l.strip() for l in text.splitlines()]
    nonempty = [l for l in raw if l]
    if not nonempty or not nonempty[0].lower().startswith('rarity:'):
        return None
    rarity = nonempty[0].split(':', 1)[1].strip().lower()
    name = nonempty[1] if len(nonempty) > 1 else ''
    base = nonempty[2] if len(nonempty) > 2 else name
    header = name if rarity == 'unique' else base

    # Explicit mods follow the "Implicits: N" line (after skipping N implicits),
    # and run until the next separator / trailer block.
    mods = []
    impl_idx = None
    n_impl = 0
    for i, l in enumerate(raw):
        if l.lower().startswith('implicits:'):
            impl_idx = i
            try:
                n_impl = int(l.split(':', 1)[1].strip())
            except ValueError:
                n_impl = 0
            break
    if impl_idx is not None:
        j = impl_idx + 1 + n_impl
        while j < len(raw):
            l = raw[j]
            if not l:
                if mods:
                    break
                j += 1
                continue
            low = l.lower()
            if low.startswith('---') or low.startswith(_ITEM_TRAILERS):
                break
            mods.append(l)
            j += 1

    out = header
    for i, m in enumerate(mods, 1):
        out += f'\n{i}. {m}'
    return out


def build_dotbuild(parsed, *, pob=None, node_id_map=None, name=None,
                    description=None, author=None, source_url=None):
    """Construct the .build JSON dict from a parsed PoB XML."""
    node_id_map = node_id_map or {}
    gem_meta = _gem_name_to_meta(pob)          # name_lower -> {'id', 'tier'}
    req_curve = _gem_req_curve(pob)

    asc_id = _ascendancy_internal_id(parsed['ascend_name'])
    full_lvl = [1, 100]
    gem_levels = parsed.get('gem_levels') or {}
    item_levels = parsed.get('item_levels') or {}

    def _gem_id(name):
        return (gem_meta.get((name or '').lower()) or {}).get('id')

    def _gem_interval(name):
        key = (name or '').lower()
        # Earliest the build actually uses the gem = the later of (a) the gem's
        # own availability from its Tier, and (b) the act/variant it first
        # appears in. Tier gives precise per-gem timing; the variant level keeps
        # it consistent with the build's progression.
        tier = (gem_meta.get(key) or {}).get('tier', 0)
        tier_lvl = tier_to_level(tier, req_curve)
        variant_lvl = gem_levels.get(key, 1)
        lvl = max(tier_lvl, variant_lvl, 1)
        return [lvl, 100]
    doc = {'name': name or parsed['class_name'] or 'Build'}
    if author:
        doc['author'] = author
    desc_parts = []
    if description:
        desc_parts.append(description)
    if source_url:
        desc_parts.append(source_url)
    if desc_parts:
        doc['description'] = '\n'.join(desc_parts)
    if asc_id:
        doc['ascendancy'] = asc_id

    # Passives: list of {"id": <passive string id>}.
    passives = []
    for nid in parsed['node_ids']:
        sid = node_id_map.get(nid)
        if sid:
            passives.append({'id': sid})
    if passives:
        doc['passives'] = passives

    # Skills: each {"id", "level_interval", "support_skills":[{"id","level_interval"}]}.
    # Exact per-gem level timing isn't recoverable from the PoB snapshot, so we
    # use the full [1, 100] interval (a valid, in-game-loadable default).
    skills = []
    for grp in parsed['skill_groups']:
        gems = grp['gems']
        if not gems:
            continue
        main_id = _gem_id(gems[0])
        if not main_id:
            continue
        entry = {'id': main_id, 'level_interval': _gem_interval(gems[0])}
        supports = []
        for nm in gems[1:]:
            gid = _gem_id(nm)
            if gid:
                supports.append({'id': gid, 'level_interval': _gem_interval(nm)})
        if supports:
            entry['support_skills'] = supports
        skills.append(entry)
    if skills:
        doc['skills'] = skills

    # Inventory: {"inventory_id", "additional_text", "level_interval", slot_x/y}.
    inventory_slots = []
    for pob_slot, inv_id in SLOT_INVENTORY_ID:
        iid = parsed['slot_map'].get(pob_slot)
        if not iid:
            continue
        item_text = parsed['items_by_id'].get(iid)
        add_text = item_additional_text(item_text)
        if add_text is None:
            continue
        ilvl = item_levels.get(pob_slot)
        inventory_slots.append({
            'additional_text': add_text,
            'inventory_id': inv_id,
            'level_interval': [ilvl, 100] if ilvl else list(full_lvl),
            'slot_x': 0,
            'slot_y': 0,
        })
    if inventory_slots:
        doc['inventory_slots'] = inventory_slots

    return doc


# -- I/O -------------------------------------------------------------------

def find_buildplanner_dir(explicit=None):
    """Return PoE2's BuildPlanner directory (does not create it)."""
    if explicit:
        return explicit
    return os.path.join(os.path.expanduser('~'), 'Documents', 'My Games',
                        'Path of Exile 2', 'BuildPlanner')


def safe_filename(s):
    """Make a string safe to use as a filename across platforms."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', (s or '').strip())
    return s[:120] or 'build'


def write_buildfile(doc, out_dir, filename):
    """Write a .build JSON to ``out_dir/filename``. Returns the full path."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=2)
    return path
