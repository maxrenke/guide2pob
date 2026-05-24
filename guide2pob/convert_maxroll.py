"""Convert Maxroll PoE2 planner builds into Path of Building 2 import codes.

Maxroll stores the full planner state as structured JSON: passive-tree node
histories, gem groups with metadata-path IDs, and equipment with base types
and mod stat dicts. This module maps that data to PoB2 XML using the same
``_document`` / ``encode`` helpers as the Mobalytics converter.
"""
import re
import html as _html

from .convert import _document, encode, _spec_xml, _esc
from .poe2data import CLASSES, resolve_class
from .scrape_maxroll import passive_variants, equipment_variants, skill_steps


# ---------------------------------------------------------------------------
# Reverse-lookup: Maxroll/PoB2 internal ID (e.g. 'Sorceress3') -> class info
# ---------------------------------------------------------------------------

# Build from poe2data.CLASSES: internalId -> ascendancy name
_INTERNAL_TO_ASC = {
    asc['internalId']: asc['name']
    for cls_info in CLASSES.values()
    for asc in cls_info['ascendancies']
}


def _asc_from_internal(internal_id):
    """Map a Maxroll ascendancy internal ID to an ascendancy display name."""
    return _INTERNAL_TO_ASC.get(internal_id)


# ---------------------------------------------------------------------------
# Passive tree
# ---------------------------------------------------------------------------

def _parse_history(history):
    """Split a Maxroll passive history into (set1_nodes, set2_nodes).

    Entries are either plain ints (weapon-set 1) or dicts with ``id`` and
    ``set`` keys where ``set == 2`` marks weapon-set 2.
    """
    set1, set2 = [], []
    for entry in (history or []):
        if isinstance(entry, dict):
            nid = str(entry.get('id', ''))
            if nid and nid.isdigit():
                (set2 if entry.get('set') == 2 else set1).append(nid)
        elif isinstance(entry, int):
            set1.append(str(entry))
    return set1, set2


# ---------------------------------------------------------------------------
# Gem / skill names
# ---------------------------------------------------------------------------

def _gem_name(gem_id, pob):
    """Convert a Maxroll gem metadata path to a display name."""
    if not gem_id:
        return ''
    # PoB data lookup: normalise path to lowercase plural form
    normalised = gem_id.lower().replace('/items/gem/', '/items/gems/')
    if pob:
        name = (pob.gems.get(normalised)
                or pob.gems.get(normalised.replace('metadata/items/gems/', '')))
        if name:
            return name
    # Fallback: parse the metadata path directly
    last = gem_id.rsplit('/', 1)[-1]
    for prefix in ('SkillGemAscendancy', 'SkillGem', 'SupportGem'):
        if last.startswith(prefix):
            last = last[len(prefix):]
            break
    # Strip trailing Two/Three/Four suffix that Maxroll adds to tiered gems
    last = re.sub(r'(?:Two|Three|Four)$', '', last)
    # CamelCase -> words
    return re.sub(r'([A-Z])', r' \1', last).strip() or gem_id


def _skill_groups_from_step(step):
    """Build ``[{label, gems:[{name, level}]}]`` from a Maxroll skill step."""
    groups = []
    for grp in step.get('skills') or []:
        gems_data = []
        for g in grp.get('gems') or []:
            gems_data.append({'id': g.get('id', ''),
                               'level': g.get('level', 20)})
        if gems_data:
            groups.append({'gems': gems_data})
    return groups


# ---------------------------------------------------------------------------
# Item base-type lookup
# ---------------------------------------------------------------------------

# Maxroll metadata-path keyword -> PoB2 base type name.
# Keyed by lowercase tail of the base path (after the last slash), using
# startswith() matching. Entries are checked in order; first match wins.
_BASE_MAP = [
    # Helmets
    ('fourhelmetint',    'Ancestral Tiara'),
    ('fourhelmetstr',    'Imperial Greathelm'),
    ('fourhelmetdex',    'Freebooter Cap'),
    ('fourhelmetstrint', 'Cryptic Crown'),
    ('fourhelmetstrdex', 'Gladiatorial Helm'),
    ('fourhelmetdexint', 'Grinning Mask'),
    # Body armours
    ('fourbodyint',      'Feathered Raiment'),
    ('fourbodystr',      'Warlord Cuirass'),
    ('fourbodydex',      'Corsair Coat'),
    ('fourbodystrint',   'Seastorm Mantle'),
    ('fourbodystrdex',   'Thane Mail'),
    ('fourbodydexint',   'Austere Garb'),
    # Gloves
    ('fourglovesint',    'Sirenscale Gloves'),
    ('fourglovesstr',    'Massive Mitts'),
    ('fourgloves',       'Polished Bracers'),     # any remaining dex/hybrid
    # Boots
    ('fourbootsint',     'Sekhema Sandals'),
    ('fourbootsstr',     'Tasalian Greaves'),
    ('fourbootsdex',     'Drakeskin Boots'),
    ('fourbootsstrint',  'Cryptic Leggings'),
    ('fourbootsstrdex',  'Blacksteel Sabatons'),
    ('fourbootsdexint',  'Grand Cuisses'),
    # Focuses
    ('fourfocus',        'Tasalian Focus'),
    # Staves
    ('fourstaff',        'Dreaming Quarterstaff'),
    # Amulets
    ('fouramulet',       'Tenebrous Amulet'),
    # Rings
    ('fourringbreach',   'Breach Ring'),
    ('fourring',         'Tenebrous Ring'),
    # Belts
    ('fourbelt',         'Fine Belt'),
    # Flasks / Charms
    ('fourflasklife',    'Ultimate Life Flask'),
    ('fourflaskmana',    'Ultimate Mana Flask'),
    ('fourflask',        'Ultimate Life Flask'),
    ('fourcharm',        'Quicksilver Flask'),
    # Jewels
    ('jeweldiamond',     'Diamond'),
    ('jewelint',         'Sapphire'),
    ('jewelstr',         'Ruby'),
    ('jeweldex',         'Emerald'),
    ('jewel',            'Diamond'),
]


def _base_type_from_path(base_path, pob=None):
    """Derive a PoB2 base type name from a Maxroll metadata base path."""
    tail = (base_path or '').rsplit('/', 1)[-1].lower()
    # Strip trailing digits, 'endgame', 'cruel', 'hardcore', 'merciless'
    tail = re.sub(r'(endgame|cruel|hardcore|merciless|\d+)$', '', tail)
    for key, base in _BASE_MAP:
        if tail.startswith(key):
            return base
    return None


# ---------------------------------------------------------------------------
# Equipment slot mapping
# ---------------------------------------------------------------------------

# Maxroll slot name -> (PoB slot name, weapon_set_index)
# weapon_set_index: 0 = primary, 1 = swap
_SLOT_MAP = {
    'Weapon':      ('Weapon 1',    0),
    'Weapon2':     ('Weapon 1',    1),
    'Offhand':     ('Weapon 2',    0),
    'Offhand2':    ('Weapon 2',    1),
    'Helm':        ('Helmet',      0),
    'BodyArmour':  ('Body Armour', 0),
    'Gloves':      ('Gloves',      0),
    'Boots':       ('Boots',       0),
    'Amulet':      ('Amulet',      0),
    'Ring':        ('Ring 1',      0),
    'Ring2':       ('Ring 2',      0),
    'Belt':        ('Belt',        0),
    'Flask1':      ('Flask 1',     0),
    'Flask2':      ('Flask 2',     0),
    'Charm1':      ('Charm 1',     0),
    'Charm2':      ('Charm 2',     0),
    'Charm3':      ('Charm 3',     0),
}


def _item_text(item, pob):
    """Render a Maxroll item dict as PoB2 item text."""
    if not item:
        return None
    name = (item.get('name') or '').strip()
    rarity = (item.get('rarity') or 'rare').lower()

    if rarity == 'unique':
        pob_rarity = 'UNIQUE'
        base = (pob.unique_bases.get(name.lower()) if pob else None) or name
    elif rarity == 'magic':
        pob_rarity = 'MAGIC'
        base = _base_type_from_path(item.get('base'), pob) or 'Item'
        name = base  # magic items use base as display name in PoB
    else:
        pob_rarity = 'RARE'
        base = _base_type_from_path(item.get('base'), pob) or 'Item'
        if not name:
            name = base

    lines = ['Rarity: ' + pob_rarity, name, base,
             '--------', 'Item Level: 82', '--------', 'Implicits: 0']
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Build a "normalised variant" dict for passing to convert.py's _spec_xml /
# _skillset_xml /_itemset_xml -- or we build our own XML directly.
# ---------------------------------------------------------------------------

def _spec_xml_maxroll(history, cls_info, tree_version, jewel_sockets_xml,
                      title=None):
    """Build <Spec> XML from a Maxroll passive-tree history."""
    set1, set2 = _parse_history(history)
    attrs = (
        'treeVersion="%s" classId="%d" ascendClassId="%d" '
        'classInternalId="%d" ascendancyInternalId="%s" '
        'secondaryAscendClassId="0" nodes="%s" masteryEffects=""'
    ) % (tree_version, cls_info['class_id'], cls_info['ascend_id'],
         cls_info['class_internal_id'], _esc(cls_info['ascend_internal_id']),
         ','.join(set1))
    if title:
        attrs = 'title="%s" %s' % (_esc(title), attrs)

    children = []
    if set2:
        children.append('<WeaponSet2 nodes="%s"/>' % ','.join(set2))
    children.append(jewel_sockets_xml or '<Sockets/>')
    children.append('<Overrides><AttributeOverride strNodes="" dexNodes="" '
                    'intNodes=""/></Overrides>')
    return '<Spec %s>\n%s\n</Spec>' % (attrs, '\n'.join(children))


def _skillset_xml_maxroll(step, pob, set_id, title=None):
    """Build <SkillSet> XML from a Maxroll skill step."""
    skills_xml = []
    for grp in _skill_groups_from_step(step):
        gems_xml = []
        for g in grp['gems']:
            name = _gem_name(g['id'], pob)
            level = g.get('level') or 20
            gems_xml.append(
                '<Gem level="%d" quality="0" qualityId="Default" '
                'enabled="true" enableGlobal1="true" enableGlobal2="true" '
                'nameSpec="%s"/>' % (level, _esc(name)))
        if gems_xml:
            first_name = _gem_name(grp['gems'][0]['id'], pob)
            skills_xml.append(
                '<Skill mainActiveSkill="1" enabled="true" label="%s">\n%s\n</Skill>'
                % (_esc(first_name), '\n'.join(gems_xml)))
    head = '<SkillSet id="%d"%s>' % (
        set_id, ' title="%s"' % _esc(title) if title else '')
    return head + '\n' + '\n'.join(skills_xml) + '\n</SkillSet>'


def _itemset_xml_maxroll(equip_variant, items_dict, pob,
                         set_id, start_item_id, jewels_dict, title=None):
    """Build item list + <ItemSet> XML from a Maxroll equipment variant.

    Returns ``(item_xml_list, itemset_xml, jewel_sockets_xml, next_item_id)``.
    ``jewels_dict`` is ``{nodeId_str: item_id_int}`` from the passive variant.
    ``items_dict`` is the top-level ``d['items']`` lookup.
    """
    item_xmls, slots = [], []
    iid = start_item_id
    slot_items = equip_variant.get('items') or {}
    has_swap = False

    for mx_slot, (pob_slot, swap) in _SLOT_MAP.items():
        raw_id = slot_items.get(mx_slot)
        if raw_id is None:
            continue
        item = items_dict.get(str(raw_id))
        txt = _item_text(item, pob)
        if not txt:
            continue
        target = (pob_slot + ' Swap') if swap else pob_slot
        if swap:
            has_swap = True
        item_xmls.append('<Item id="%d">\n%s\n</Item>' % (iid, _esc(txt)))
        slots.append('<Slot name="%s" itemId="%d"/>' % (target, iid))
        iid += 1

    # Jewels in passive tree sockets
    jewel_sockets = []
    for node_id_str, item_id_int in (jewels_dict or {}).items():
        item = items_dict.get(str(item_id_int))
        txt = _item_text(item, pob)
        if not txt:
            continue
        item_xmls.append('<Item id="%d">\n%s\n</Item>' % (iid, _esc(txt)))
        jewel_sockets.append(
            '<Socket nodeId="%s" itemId="%d"/>' % (node_id_str, iid))
        iid += 1

    # Empty sockets for jewel-socket nodes with no jewel
    if pob and hasattr(pob, 'jewel_socket_nodes'):
        filled = {s.split('"')[1] for s in jewel_sockets}
        for node_id_str in jewels_dict or {}:
            pass  # already covered above
        # Also emit empties for any passive socket node that has no jewel
        # (we skip this for Maxroll since we don't have a full node list here)

    jewel_sockets_xml = ('<Sockets>%s</Sockets>' % ''.join(jewel_sockets)
                         if jewel_sockets else '<Sockets/>')

    head = '<ItemSet useSecondWeaponSet="%s" id="%d"%s>' % (
        'true' if has_swap else 'false', set_id,
        ' title="%s"' % _esc(title) if title else '')
    itemset_xml = head + '\n' + '\n'.join(slots) + '\n</ItemSet>'
    return item_xmls, itemset_xml, jewel_sockets_xml, iid


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _resolve(planner, profile, class_override, ascendancy_override):
    asc = ascendancy_override
    if not asc and not class_override:
        internal = (planner.get('ascendancy')
                    or profile.get('ascendancy') or '')
        asc = _asc_from_internal(internal) if internal else None
    return resolve_class(class_override, asc)


def convert(planner, profile, variant_idx=None, pob=None,
            class_override=None, ascendancy_override=None,
            level=90, title=None, notes=None):
    """Convert one Maxroll planner variant into a standalone PoB2 build code.

    ``variant_idx`` selects which passive/equipment phase to use (0-based).
    Defaults to the last (most complete) phase.
    """
    p_variants = passive_variants(planner)
    e_variants = equipment_variants(planner)
    s_steps = skill_steps(planner)
    items_dict = planner.get('items') or {}

    idx = variant_idx if variant_idx is not None else max(0, len(p_variants) - 1)
    p_var = p_variants[idx] if idx < len(p_variants) else (p_variants[-1] if p_variants else {})
    e_var = e_variants[idx] if idx < len(e_variants) else (e_variants[-1] if e_variants else {})
    s_step = s_steps[idx] if idx < len(s_steps) else (s_steps[-1] if s_steps else {})

    info = _resolve(planner, profile, class_override, ascendancy_override)
    tree_version = pob.tree_version if pob else '0_4'

    jewels = p_var.get('jewels') or {}
    item_xmls, itemset, jewel_sockets_xml, _ = _itemset_xml_maxroll(
        e_var, items_dict, pob, set_id=1, start_item_id=1,
        jewels_dict=jewels, title=title)
    skillset = _skillset_xml_maxroll(s_step, pob, set_id=1, title=title)
    spec = _spec_xml_maxroll(
        p_var.get('history'), info, tree_version, jewel_sockets_xml, title=title)

    xml = _document(info, level, [spec], [skillset], item_xmls, [itemset],
                    notes=notes)
    history = p_var.get('history') or []
    set1, _ = _parse_history(history)
    n_skills = len(_skill_groups_from_step(s_step))
    return {
        'code': encode(xml),
        'xml': xml,
        'class': info['class_name'],
        'ascendancy': info['ascend_name'],
        'tree_version': tree_version,
        'node_count': len(set1),
        'skill_count': n_skills,
        'detected_ascendancy': False,
    }


def convert_merged(planner, profile, pob=None, class_override=None,
                   ascendancy_override=None, level=90, titles=None,
                   notes=None):
    """Merge all Maxroll passive/equipment/skill phases into one PoB2 build.

    Each phase becomes a switchable Tree spec, Skill Set, and Item Set.
    Phases are kept in source order (earliest to latest).
    """
    p_variants = passive_variants(planner)
    e_variants = equipment_variants(planner)
    s_steps = skill_steps(planner)
    items_dict = planner.get('items') or {}
    n = max(len(p_variants), len(e_variants), len(s_steps), 1)

    if not titles:
        # Use the longest-named list available for title generation
        longest = max(p_variants, e_variants, s_steps,
                      key=lambda lst: len(lst))
        titles = [(v.get('name') if isinstance(v, dict) else f'Phase {i}')
                  for i, v in enumerate(longest)]
        # Pad if needed
        while len(titles) < n:
            titles.append(f'Phase {len(titles)}')

    info = _resolve(planner, profile, class_override, ascendancy_override)
    tree_version = pob.tree_version if pob else '0_4'

    specs, skillsets, all_items, itemsets = [], [], [], []
    next_id = 1

    for i in range(n):
        p_var = p_variants[i] if i < len(p_variants) else (p_variants[-1] if p_variants else {})
        e_var = e_variants[i] if i < len(e_variants) else (e_variants[-1] if e_variants else {})
        s_step = s_steps[i] if i < len(s_steps) else (s_steps[-1] if s_steps else {})
        title_i = titles[i] if i < len(titles) else f'Phase {i}'

        jewels = p_var.get('jewels') or {}
        item_xmls, itemset, jewel_sockets_xml, next_id = _itemset_xml_maxroll(
            e_var, items_dict, pob, set_id=i + 1, start_item_id=next_id,
            jewels_dict=jewels, title=title_i)
        skillset = _skillset_xml_maxroll(s_step, pob, set_id=i + 1, title=title_i)
        spec = _spec_xml_maxroll(
            p_var.get('history'), info, tree_version, jewel_sockets_xml,
            title=title_i)

        specs.append(spec)
        skillsets.append(skillset)
        all_items += item_xmls
        itemsets.append(itemset)

    xml = _document(info, level, specs, skillsets, all_items, itemsets,
                    notes=notes)
    return {
        'code': encode(xml),
        'xml': xml,
        'class': info['class_name'],
        'ascendancy': info['ascend_name'],
        'tree_version': tree_version,
        'variant_count': n,
        'node_count': sum(len(_parse_history(p.get('history'))[0])
                          for p in p_variants),
        'detected_ascendancy': False,
    }
