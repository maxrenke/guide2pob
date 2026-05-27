"""Generate Path of Exile 2 in-game .build files from PoB build XML.

The .build format is the JSON document PoE2's Build Planner reads from
``Documents/My Games/Path of Exile 2/Preferences/BuildPlanner/``. Schema:
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

# PoB slot name -> .build inventory_id (per dev docs example).
SLOT_INVENTORY_ID = {
    'Weapon 1':    'Weapon1',
    'Weapon 2':    'Weapon2',
    'Helmet':      'Helm1',
    'Body Armour': 'BodyArmour1',
    'Gloves':      'Gloves1',
    'Boots':       'Boots1',
    'Belt':        'Belt1',
    'Amulet':      'Amulet1',
    'Ring 1':      'Ring1',
    'Ring 2':      'Ring2',
}


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
    key = id(pob)
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


def build_dotbuild(parsed, *, pob=None, node_id_map=None, name=None,
                    description=None, author=None, source_url=None):
    """Construct the .build JSON dict from a parsed PoB XML."""
    node_id_map = node_id_map or {}
    gem_map = _gem_name_to_id(pob)

    asc_id = _ascendancy_internal_id(parsed['ascend_name'])
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

    passives = []
    for nid in parsed['node_ids']:
        sid = node_id_map.get(nid)
        if sid:
            passives.append(sid)
    if passives:
        doc['passives'] = passives

    skills = []
    for grp in parsed['skill_groups']:
        gems = grp['gems']
        if not gems:
            continue
        main_id = gem_map.get(gems[0].lower())
        if not main_id:
            continue
        entry = {'id': main_id}
        supports = []
        for nm in gems[1:]:
            gid = gem_map.get(nm.lower())
            if gid:
                supports.append(gid)
        if supports:
            entry['support_skills'] = supports
        skills.append(entry)
    if skills:
        doc['skills'] = skills

    inventory_slots = []
    for pob_slot, inv_id in SLOT_INVENTORY_ID.items():
        iid = parsed['slot_map'].get(pob_slot)
        if not iid:
            continue
        item_text = parsed['items_by_id'].get(iid)
        item_name, is_unique = _item_name_and_unique(item_text)
        entry = {'inventory_id': inv_id}
        if is_unique and item_name:
            entry['unique_name'] = item_name
        inventory_slots.append(entry)
    if inventory_slots:
        doc['inventory_slots'] = inventory_slots

    return doc


# -- I/O -------------------------------------------------------------------

def find_buildplanner_dir(explicit=None):
    """Return PoE2's BuildPlanner directory (does not create it)."""
    if explicit:
        return explicit
    return os.path.join(os.path.expanduser('~'), 'Documents', 'My Games',
                        'Path of Exile 2', 'Preferences', 'BuildPlanner')


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
