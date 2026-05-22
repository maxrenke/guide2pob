"""Convert a Mobalytics build variant into a Path of Building 2 import code.

A PoB import code is standard base64 of zlib-deflated build XML. Mobalytics
passive node slugs (``node-62677``) use the same numeric IDs as PoB's passive
tree, so the tree maps across directly.
"""
import re
import zlib
import base64
import html as _html
from collections import Counter

from .poe2data import resolve_class

# Mobalytics equipment slot -> PoB2 item slot.
_SLOT_MAP = {
    'mainHand': 'Weapon 1', 'offHand': 'Weapon 2', 'helmet': 'Helmet',
    'body': 'Body Armour', 'gloves': 'Gloves', 'boots': 'Boots',
    'amulet': 'Amulet', 'leftRing': 'Ring 1', 'rightRing': 'Ring 2',
    'belt': 'Belt', 'flask1': 'Flask 1', 'flask2': 'Flask 2',
    'charm1': 'Charm 1', 'charm2': 'Charm 2', 'charm3': 'Charm 3',
}


def _esc(s):
    return _html.escape(str(s), quote=True)


# -- passive tree ---------------------------------------------------------
def _tree_nodes(variant):
    """Return the allocated passive node IDs (main tree + ascendancy)."""
    tree = variant.get('passiveTree') or {}
    out = []
    for group in ('mainTree', 'ascendancyTree'):
        for slug in (tree.get(group) or {}).get('selectedSlugs', []):
            nid = str(slug).replace('node-', '')
            if nid.isdigit():
                out.append(nid)
    return out


def _ascendancy_node_ids(variant):
    tree = variant.get('passiveTree') or {}
    out = []
    for slug in (tree.get('ascendancyTree') or {}).get('selectedSlugs', []):
        nid = str(slug).replace('node-', '')
        if nid.isdigit():
            out.append(nid)
    return out


def detect_ascendancy(variant, pob):
    """Infer the ascendancy name from allocated ascendancy nodes."""
    if not pob:
        return None
    votes = Counter()
    for nid in _ascendancy_node_ids(variant):
        asc = pob.ascendancy_of_node(nid)
        if asc:
            votes[asc] += 1
    return votes.most_common(1)[0][0] if votes else None


# -- gems -----------------------------------------------------------------
def gem_name(slug, pob):
    """Resolve a Mobalytics gem slug to a PoB gem name."""
    s = slug.lower()
    if pob:
        gems = pob.gems
        candidates = [
            s,
            s + 'player',
            re.sub(r'(player|playertwo|playerthree|playerfour)$', '', s),
            'support' + re.sub(r'^support', '',
                                re.sub(r'(player.*)$', '', s)) + 'player',
        ]
        for c in candidates:
            if c in gems:
                return gems[c]
    # Fallback: prettify the slug.
    core = re.sub(r'^support', '',
                  re.sub(r'(player.*|two|three|four)$', '', s))
    return core.title() or slug


def _skill_groups(variant):
    groups = []
    for g in (variant.get('skillGems') or {}).get('gems', []):
        act = g.get('activeSkill') or {}
        gems = [{'slug': act.get('gemSlug', ''), 'name': act.get('name', '')}]
        for sub in g.get('subSkills') or []:
            gems.append({'slug': sub.get('gemSlug', ''), 'name': ''})
        groups.append({'label': act.get('name', 'Skill'), 'gems': gems})
    return groups


# -- items ----------------------------------------------------------------
def _common_item(slot):
    """Unwrap a Mobalytics equipment slot to its item dict."""
    if not slot:
        return None
    if slot.get('commonItem'):
        return slot['commonItem']
    if slot.get('uniqueItem'):
        return slot['uniqueItem']
    for ws in ('set1', 'set2'):  # weapon-set slots
        if slot.get(ws):
            inner = slot[ws].get('commonItem') or slot[ws].get('uniqueItem')
            if inner:
                return inner
    return None


def _item_text(slot, pob):
    ci = _common_item(slot)
    if not ci:
        return None
    name = ci.get('name') or 'Item'
    rarity = 'UNIQUE' if ci.get('isUnique') else 'RARE'
    lines = ['Rarity: ' + rarity, name]
    if rarity == 'UNIQUE':
        base = pob.unique_bases.get(name.lower()) if pob else None
        lines.append(base or name)
    else:
        lines.append(name)  # Mobalytics reports rares by base type
    implicits = ci.get('implicitDescriptions') or []
    lines.append('Implicits: %d' % len(implicits))
    lines += [d['description'] for d in implicits]
    lines += [d['description'] for d in (ci.get('explicitDescriptions') or [])]
    return '\n'.join(lines)


# -- XML ------------------------------------------------------------------
def variant_to_xml(variant, class_name, class_id, ascend_id,
                   tree_version, level=90):
    nodes = ','.join(_tree_nodes(variant))

    skills = []
    for grp in _skill_groups(variant):
        gem_xml = []
        for g in grp['gems']:
            nm = g['name'] or gem_name(g['slug'], _CURRENT_POB[0])
            gem_xml.append(
                '<Gem level="20" quality="0" qualityId="Default" enabled="true" '
                'enableGlobal1="true" enableGlobal2="true" nameSpec="%s"/>'
                % _esc(nm))
        skills.append('<Skill mainActiveSkill="1" enabled="true" label="%s">\n%s\n</Skill>'
                       % (_esc(grp['label']), '\n'.join(gem_xml)))

    items, slots = [], []
    equipment = variant.get('equipment') or {}
    for moba_slot, pob_slot in _SLOT_MAP.items():
        txt = _item_text(equipment.get(moba_slot), _CURRENT_POB[0])
        if not txt:
            continue
        iid = len(items) + 1
        items.append('<Item id="%d">\n%s\n</Item>' % (iid, _esc(txt)))
        slots.append('<Slot name="%s" itemId="%d"/>' % (pob_slot, iid))

    return '\n'.join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<PathOfBuilding>',
        '<Build level="%d" className="%s" ascendClassName="%s" '
        'mainSocketGroup="1" viewMode="TREE">' % (
            level, _esc(class_name), _esc(_ascend_name(class_name, ascend_id))),
        '</Build>',
        '<Import/>',
        '<Skills sortGemsByDPS="true" activeSkillSet="1">',
        '<SkillSet id="1">',
        '\n'.join(skills),
        '</SkillSet>',
        '</Skills>',
        '<Tree activeSpec="1">',
        '<Spec treeVersion="%s" classId="%d" ascendClassId="%d" nodes="%s" '
        'masteryEffects="">' % (tree_version, class_id, ascend_id, nodes),
        '</Spec>',
        '</Tree>',
        '<Items activeItemSet="1">',
        '\n'.join(items),
        '<ItemSet useSecondWeaponSet="false" id="1">',
        '\n'.join(slots),
        '</ItemSet>',
        '</Items>',
        '<Config/>',
        '</PathOfBuilding>',
    ])


def _ascend_name(class_name, ascend_id):
    from .poe2data import CLASSES
    if ascend_id and class_name in CLASSES:
        ascs = CLASSES[class_name]['ascendancies']
        if 1 <= ascend_id <= len(ascs):
            return ascs[ascend_id - 1]
    return 'None'


def encode(xml):
    """Encode build XML as a Path of Building import code."""
    return base64.b64encode(zlib.compress(xml.encode('utf-8'), 9)).decode('ascii')


# convert() passes the active PoBData to the XML builder without threading it
# through every signature.
_CURRENT_POB = [None]


def convert(variant, pob=None, class_override=None,
            ascendancy_override=None, level=90):
    """Convert one build variant. Returns dict with code, xml, and metadata."""
    _CURRENT_POB[0] = pob
    ascendancy = ascendancy_override or detect_ascendancy(variant, pob)
    class_name, class_id, ascend_id = resolve_class(class_override, ascendancy)
    tree_version = pob.tree_version if pob else '0_4'
    xml = variant_to_xml(variant, class_name, class_id, ascend_id,
                         tree_version, level)
    return {
        'code': encode(xml),
        'xml': xml,
        'class': class_name,
        'ascendancy': _ascend_name(class_name, ascend_id),
        'tree_version': tree_version,
        'node_count': len(_tree_nodes(variant)),
        'skill_count': len(_skill_groups(variant)),
        'detected_ascendancy': bool(ascendancy and not ascendancy_override),
    }
