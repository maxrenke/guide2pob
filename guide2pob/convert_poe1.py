"""Convert Mobalytics PoE1 build data to Path of Building import codes.

Mobalytics PoE1 guides embed a complete PoB import code (pobCode) at the
document level. By default this is decoded and returned directly - it is
far more accurate than reconstructing from the structured JSON because it
includes precise item prefixes/suffixes, gem variantIds, and masteries.

For per-variant or merged output the structured data is used instead:
  - Equipment:  genericBuilder.slots[].gameEntity
  - Skills:     skills.gemGroups[].{slotSlug, gems}
  - Passive:    passiveTree.{mainTree, ascendancyTree, masteries, jewels}

The class and ascendancy are always read from the decoded pobCode XML
since all variants share the same class/ascendancy progression.
"""
import re
import zlib
import base64
import html as _html

from .poe1data import resolve_class

# Mobalytics PoE1 slot name -> PoB1 slot name.
# Grafts (Sanctum mechanic) have no PoB equivalent and are skipped.
_POE1_SLOT_MAP = {
    'mainHand': 'Weapon 1', 'offHand': 'Weapon 2',
    'helmet': 'Helmet',     'body': 'Body Armour',
    'gloves': 'Gloves',     'boots': 'Boots',
    'amulet': 'Amulet',     'belt': 'Belt',
    'leftRing': 'Ring 1',   'rightRing': 'Ring 2',
    'quiver': 'Quiver',
    'flask1': 'Flask 1', 'flask2': 'Flask 2', 'flask3': 'Flask 3',
    'flask4': 'Flask 4', 'flask5': 'Flask 5',
}


def _esc(s):
    return _html.escape(str(s), quote=True)


# -- pobCode path -----------------------------------------------------------

def decode_pobcode(doc):
    """Decode the URL-safe-base64 + zlib pobCode embedded in a PoE1 doc."""
    code = doc.get('pobCode')
    if not code:
        raise ValueError("no pobCode in document")
    std = code.replace('-', '+').replace('_', '/')
    return zlib.decompress(base64.b64decode(std + '==')).decode('utf-8')


def _class_info_from_xml(xml):
    """Pull className and ascendClassName out of a decoded PoB XML string."""
    m = re.search(r'className="([^"]+)"', xml)
    class_name = m.group(1) if m else None
    m = re.search(r'ascendClassName="([^"]+)"', xml)
    ascend_name = m.group(1) if m else None
    return class_name, ascend_name


# -- passive tree -----------------------------------------------------------

def _slug_ids(slugs):
    """['node-123', 'node-abc', 'node-456'] -> ['123', '456']."""
    out = []
    for slug in slugs or []:
        nid = str(slug).replace('node-', '')
        if nid.isdigit():
            out.append(nid)
    return out


def _tree_nodes(variant):
    """All allocated passive node IDs (main tree + ascendancy + alternate)."""
    pt = variant.get('passiveTree') or {}
    out = []
    for key in ('mainTree', 'ascendancyTree', 'alternateAscendancyTree'):
        out += _slug_ids((pt.get(key) or {}).get('selectedSlugs'))
    return out


def _mastery_string(variant):
    """Encode mastery selections as '{nodeId,effectId},...' (PoB1 format)."""
    pt = variant.get('passiveTree') or {}
    parts = []
    for m in pt.get('masteries') or []:
        node_slug = (m.get('passiveSkillNode') or {}).get('slug', '')
        effect_slug = str((m.get('mastery') or {}).get('slug', ''))
        nid = node_slug.replace('node-', '')
        if nid.isdigit() and effect_slug:
            parts.append('{%s,%s}' % (nid, effect_slug))
    return ','.join(parts)


# -- skills -----------------------------------------------------------------

def _skill_groups(variant):
    """Extract gem groups from PoE1 skills.gemGroups structure."""
    skills = variant.get('skills') or {}
    groups = []
    for g in skills.get('gemGroups') or []:
        slot = g.get('slotSlug') or ''
        label = g.get('label') or slot or 'Skill'
        gems = []
        for gem_entry in g.get('gems') or []:
            obj = gem_entry.get('skillGemObject') or {}
            name = (obj.get('data') or {}).get('name', '')
            if name:
                gems.append(name)
        if gems:
            groups.append({'label': label, 'slot': slot, 'gems': gems})
    return groups


# -- items ------------------------------------------------------------------

def _item_text(slot_entry):
    """Render a PoE1 genericBuilder slot entry to PoB item text.

    Slot data structure:
      gameSlotSlug: "mainHand" | "flask1" | ...
      gameEntity:
        title:     base type for rares, unique name for uniques
        data:
          name:    "New Item" (rare/magic generated) or unique/magic name
          rarity:  "UNIQUE" | "MAGIC" | "RARE" | null
          subTitle: base type for uniques, null for rares
          explicitMods: [{text: "..."}]
          implicitMods: [{text: "..."}] | null
    """
    ge = slot_entry.get('gameEntity')
    if not ge:
        return None
    data = ge.get('data') or {}
    rarity = (data.get('rarity') or 'RARE').upper()
    title = ge.get('title') or ''
    sub_title = data.get('subTitle') or ''
    item_name = data.get('name') or ''

    if rarity == 'UNIQUE':
        name = title          # e.g. "Headhunter"
        base = sub_title or title
    elif rarity == 'MAGIC':
        name = item_name or title   # full affixed name
        base = title                # base type
    else:
        # RARE: Mobalytics reports title = base type, name = "New Item"
        name = item_name or 'New Item'
        base = title

    implicits = data.get('implicitMods') or []
    explicits = data.get('explicitMods') or []

    lines = ['Rarity: ' + rarity, name, base, '--------', 'Item Level: 82', '--------']
    lines.append('Implicits: %d' % len(implicits))
    lines += [m.get('text', '') for m in implicits]
    if implicits and explicits:
        lines.append('--------')
    lines += [m.get('text', '') for m in explicits]
    return '\n'.join(lines)


def _jewel_text(jewel_entry):
    """Render a passiveTree.jewels entry to PoB item text.

    Jewel data structure:
      nodeSlug: "node-61834"
      jewel:
        data:
          name:     "New Item" (rare) or unique name
          subTitle: "Viridian Jewel" (base type)
          rarity:   "UNIQUE" | "RARE" | null
          explicitMods: [{text: "..."}]
          implicitMods: [{text: "..."}] | null
        entityV2:
          name: "Viridian Jewel" (fallback base type)
    """
    jewel = jewel_entry.get('jewel') or {}
    data = jewel.get('data') or {}
    entity = jewel.get('entityV2') or {}

    rarity = (data.get('rarity') or 'RARE').upper()
    sub_title = data.get('subTitle') or entity.get('name') or 'Jewel'
    item_name = data.get('name') or ''

    if rarity == 'UNIQUE':
        name = item_name or sub_title
        base = sub_title
    else:
        name = item_name or 'New Item'
        base = sub_title

    implicits = data.get('implicitMods') or []
    explicits = data.get('explicitMods') or []

    lines = ['Rarity: ' + rarity, name, base, '--------', 'Item Level: 82', '--------']
    lines.append('Implicits: %d' % len(implicits))
    lines += [m.get('text', '') for m in implicits]
    if implicits and explicits:
        lines.append('--------')
    lines += [m.get('text', '') for m in explicits]
    return '\n'.join(lines)


# -- XML components ---------------------------------------------------------

def _spec_xml(variant, cls_info, tree_version, title=None):
    nodes = ','.join(_tree_nodes(variant))
    mastery = _mastery_string(variant)
    attrs = (
        'treeVersion="%s" classId="%d" ascendClassId="%d" masteryEffects="%s" nodes="%s"'
    ) % (tree_version, cls_info['class_id'], cls_info['ascend_id'], mastery, nodes)
    if title:
        attrs = 'title="%s" %s' % (_esc(title), attrs)

    sockets_xml = variant.get('_jewel_sockets_xml', '<Sockets/>')
    return '<Spec %s>\n%s\n</Spec>' % (attrs, sockets_xml)


def _skillset_xml(variant, set_id, title=None):
    groups = _skill_groups(variant)
    skills_xml = []
    for g in groups:
        gems_xml = '\n'.join(
            '<Gem level="20" quality="20" qualityId="Default" enabled="true" nameSpec="%s"/>'
            % _esc(nm)
            for nm in g['gems']
        )
        slot_attr = ' slot="%s"' % _esc(g['slot']) if g['slot'] else ''
        skills_xml.append(
            '<Skill mainActiveSkill="1" enabled="true" label="%s"%s>\n%s\n</Skill>'
            % (_esc(g['label']), slot_attr, gems_xml)
        )
    head = '<SkillSet id="%d"%s>' % (
        set_id, ' title="%s"' % _esc(title) if title else '')
    return head + '\n' + '\n'.join(skills_xml) + '\n</SkillSet>'


def _itemset_xml(variant, set_id, start_item_id, title=None):
    """Render items + jewels for one variant.

    Returns (item_xml_list, itemset_xml, next_item_id).
    Side-effect: sets variant['_jewel_sockets_xml'] for _spec_xml to consume.
    """
    items, slots = [], []
    iid = start_item_id

    gb = variant.get('genericBuilder') or {}
    for slot_entry in gb.get('slots') or []:
        slug = slot_entry.get('gameSlotSlug', '')
        pob_slot = _POE1_SLOT_MAP.get(slug)
        if not pob_slot:
            continue  # skip grafts and unknown slots
        txt = _item_text(slot_entry)
        if not txt:
            continue
        items.append('<Item id="%d">\n%s\n</Item>' % (iid, _esc(txt)))
        slots.append('<Slot name="%s" itemId="%d"/>' % (pob_slot, iid))
        iid += 1

    # Jewels
    pt = variant.get('passiveTree') or {}
    jewel_sockets = []
    for je in pt.get('jewels') or []:
        node_ids = _slug_ids([je.get('nodeSlug', '')])
        if not node_ids:
            continue
        txt = _jewel_text(je)
        items.append('<Item id="%d">\n%s\n</Item>' % (iid, _esc(txt)))
        jewel_sockets.append('<Socket nodeId="%s" itemId="%d"/>' % (node_ids[0], iid))
        iid += 1

    sockets_xml = ('<Sockets>%s</Sockets>' % ''.join(jewel_sockets)
                   if jewel_sockets else '<Sockets/>')
    variant['_jewel_sockets_xml'] = sockets_xml

    head = '<ItemSet id="%d"%s>' % (
        set_id, ' title="%s"' % _esc(title) if title else '')
    itemset_xml = head + '\n' + '\n'.join(slots) + '\n</ItemSet>'
    return items, itemset_xml, iid


def _document(cls_info, level, specs, skillsets, all_items, itemsets,
              notes=None, tree_version='3_25'):
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<PathOfBuilding>',
        # targetVersion="3_0" tells PoB this is a modern PoE1 build format.
        '<Build targetVersion="3_0" level="%d" className="%s" ascendClassName="%s" '
        'mainSocketGroup="1" viewMode="TREE">' % (
            level, _esc(cls_info['class_name']), _esc(cls_info['ascend_name'])),
        '<PlayerStat stat="Level" value="%d"/>' % level,
        '</Build>',
        '<Import/>',
        '<Skills sortGemsByDPS="true" activeSkillSet="1">',
        '\n'.join(skillsets),
        '</Skills>',
        '<Tree activeSpec="1">',
        '\n'.join(specs),
        '</Tree>',
        '<Items activeItemSet="1">',
        '\n'.join(all_items),
        '\n'.join(itemsets),
        '</Items>',
    ]
    if notes:
        parts += ['<Notes>%s</Notes>' % _esc(notes)]
    parts += ['<Config/>', '</PathOfBuilding>']
    return '\n'.join(parts)


def encode(xml):
    """Encode build XML as a Path of Building import code (standard base64)."""
    return base64.b64encode(zlib.compress(xml.encode('utf-8'), 9)).decode('ascii')


# -- public API -------------------------------------------------------------

def _get_cls_info(doc, class_override=None, ascendancy_override=None):
    """Read class info from the embedded pobCode XML, with optional overrides."""
    class_name, ascend_name = class_override, ascendancy_override
    if not (class_name and ascend_name):
        try:
            xml = decode_pobcode(doc)
            cn, an = _class_info_from_xml(xml)
            class_name = class_name or cn
            ascend_name = ascend_name or an
        except Exception:
            pass
    return resolve_class(class_name, ascend_name)


def convert(doc, variant_idx=None, notes=None, level=90,
            class_override=None, ascendancy_override=None,
            tree_version='3_25'):
    """Convert a PoE1 Mobalytics document to a PoB import code.

    variant_idx=None (default): decode and return the embedded pobCode
      directly. This is the highest-quality output.

    variant_idx=N: reconstruct XML from variant N's structured JSON data.
      Use this when you specifically need a single progression step.
    """
    from .scrape import build_variants

    if variant_idx is None:
        # Best path: use the embedded complete PoB build.
        xml = decode_pobcode(doc)
        cls_name, asc_name = _class_info_from_xml(xml)
        if notes:
            inject = '<Notes>%s</Notes>\n' % _esc(notes)
            # Remove any existing <Notes> element before injecting so we don't
            # produce two <Notes> blocks when the original pobCode already has one.
            xml = re.sub(r'<Notes>.*?</Notes>\s*', '', xml, flags=re.S)
            xml = xml.replace('</PathOfBuilding>', inject + '</PathOfBuilding>', 1)
        return {
            'code': encode(xml),
            'xml': xml,
            'class': cls_name or '?',
            'ascendancy': asc_name or 'None',
            'source': 'pobCode',
        }

    variants = build_variants(doc)
    if not variants:
        raise ValueError("no variants in document")
    variant = variants[variant_idx % len(variants)]
    cls_info = _get_cls_info(doc, class_override, ascendancy_override)

    items, itemset, _ = _itemset_xml(variant, 1, 1)
    try:
        spec = _spec_xml(variant, cls_info, tree_version)
        skillset = _skillset_xml(variant, 1)
    finally:
        variant.pop('_jewel_sockets_xml', None)

    xml = _document(cls_info, level, [spec], [skillset], items, [itemset],
                    notes=notes, tree_version=tree_version)
    return {
        'code': encode(xml),
        'xml': xml,
        'class': cls_info['class_name'],
        'ascendancy': cls_info['ascend_name'],
        'node_count': len(_tree_nodes(variant)),
        'source': 'structured',
    }


def convert_merged(doc, notes=None, level=90, class_override=None,
                   ascendancy_override=None, titles=None,
                   progression_order=True, tree_version='3_25'):
    """Merge all PoE1 variants into one build with switchable specs/sets."""
    from .scrape import build_variants

    variants = build_variants(doc)
    if not variants:
        raise ValueError("no variants in document")

    titles = titles or ['Variant %d' % i for i in range(len(variants))]
    cls_info = _get_cls_info(doc, class_override, ascendancy_override)

    if progression_order:
        order = sorted(range(len(variants)),
                       key=lambda i: len(_tree_nodes(variants[i])))
        variants = [variants[i] for i in order]
        titles = [titles[i] for i in order]

    specs, skillsets, all_items, itemsets = [], [], [], []
    next_id = 1
    for i, (variant, title) in enumerate(zip(variants, titles)):
        items, itemset, next_id = _itemset_xml(variant, i + 1, next_id, title)
        try:
            spec = _spec_xml(variant, cls_info, tree_version, title)
            skillset = _skillset_xml(variant, i + 1, title)
        finally:
            variant.pop('_jewel_sockets_xml', None)
        specs.append(spec)
        skillsets.append(skillset)
        all_items += items
        itemsets.append(itemset)

    xml = _document(cls_info, level, specs, skillsets, all_items, itemsets,
                    notes=notes, tree_version=tree_version)
    return {
        'code': encode(xml),
        'xml': xml,
        'class': cls_info['class_name'],
        'ascendancy': cls_info['ascend_name'],
        'variant_count': len(variants),
        'source': 'structured',
    }
