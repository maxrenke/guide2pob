"""Convert Mobalytics build variants into Path of Building 2 import codes.

A PoB import code is standard base64 of zlib-deflated build XML. Mobalytics
passive node slugs (``node-62677``) use the same numeric IDs as PoB's passive
tree, so the tree maps across directly.

Two output shapes are supported:

* ``convert``        - one variant -> one standalone build code.
* ``convert_merged`` - several variants -> a single build code where each
  variant is a switchable Tree spec, Item Set, and Skill Set.

This module also encodes the bits of a Mobalytics build that PoB's tree and
item tabs care about beyond the headline equipment list: weapon-set 2 items,
weapon-set tree allocations, attribute-node choices (str/dex/int picks),
jewels in tree sockets, item runes / soul cores, and amulet anointments.
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
_WEAPON_SLOTS = ('mainHand', 'offHand')

# Fallback unique-item base types for when no PoB2 install is available.
# Maps lowercase unique name -> PoB2 base type string.
# Populated from PoB2's Data/Uniques/*.lua; extend as needed.
_FALLBACK_UNIQUE_BASES: dict = {
    # Helmets
    "atziri's disdain":      "Jade Husk",
    "crown of eyes":         "Rusted Coif",
    "the vertex":            "Vaal Mask",
    "brinerot whalers":      "Wrapped Boots",      # note: actually boots
    # Body armour
    "tabula rasa":           "Simple Robe",
    "cloak of defiance":     "Lacquered Garb",
    "shavronne's wrappings": "Spidersilk Robe",
    # Gloves
    "doedre's tenure":       "Scholar's Gloves",
    "aurora's hands":        "Sorcerer Gloves",
    # Boots
    "wanderlust":            "Wool Shoes",
    "rainbowstride":         "Conjurer Boots",
    # Amulets
    "the brass dome":        "Iron Plate",          # note: body in PoE1; skip if wrong
    "presence of chayula":   "Onyx Amulet",
    "malachai's artifice":   "Paua Ring",           # note: ring in PoE1
    # Rings
    "snakepit":              "Coral Ring",
    "winterheart":           "Gold Ring",
    "the taming":            "Prismatic Ring",
    "heartbound loop":       "Moonstone Ring",
    # Belts
    "darkness enthroned":    "Studded Belt",
    "headhunter":            "Leather Belt",
    "wurm's molt":           "Leather Belt",
    # Wands
    "lifesprig":             "Driftwood Wand",
    "void battery":          "Prophecy Wand",
    # Staves / other weapons
    "the annihilating light": "Judgement Staff",
    "atziri's acuity":       "Vaal Gloves",         # gloves
}


def _esc(s):
    return _html.escape(str(s), quote=True)


# -- passive tree ---------------------------------------------------------
def _slug_ids(slugs):
    """Convert ['node-123', 'node-abc', 'node-456'] -> ['123', '456']."""
    out = []
    for slug in slugs or []:
        nid = str(slug).replace('node-', '')
        if nid.isdigit():
            out.append(nid)
    return out


def _tree_nodes(variant):
    """Return all allocated passive node IDs (main tree + ascendancy)."""
    tree = variant.get('passiveTree') or {}
    out = []
    for group in ('mainTree', 'ascendancyTree'):
        out += _slug_ids((tree.get(group) or {}).get('selectedSlugs'))
    return out


def _ascendancy_node_ids(variant):
    return _slug_ids(
        ((variant.get('passiveTree') or {}).get('ascendancyTree') or {})
        .get('selectedSlugs'))


def _weapon_set_tree_nodes(variant):
    """Weapon-set node allocations as {1: [ids], 2: [ids]} (only sets with data)."""
    tree = variant.get('passiveTree') or {}
    sets = {}
    for idx, key in ((1, 'set1Tree'), (2, 'set2Tree')):
        ids = _slug_ids((tree.get(key) or {}).get('selectedSlugs'))
        if ids:
            sets[idx] = ids
    return sets


def _attribute_overrides(variant):
    """Per-attribute lists of node IDs PoB needs for str/dex/int picks."""
    by_attr = {'str': [], 'dex': [], 'int': []}
    for entry in (variant.get('passiveTree') or {}).get('attributeNodes') or []:
        attr = entry.get('attribute')
        ids = _slug_ids([entry.get('nodeSlug', '')])
        if attr in by_attr and ids:
            by_attr[attr].extend(ids)
    return by_attr


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
    s = (slug or '').lower()
    if pob and s:
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
def _humanize_rune(slug):
    """soulcore-runeenhancegreater -> 'Soulcore Runeenhancegreater'."""
    return ' '.join(p.title() for p in str(slug).replace('_', '-').split('-')
                    if p)


def _common_item(slot):
    """Unwrap a Mobalytics equipment slot to its item dict."""
    if not slot:
        return None
    if slot.get('commonItem'):
        return slot['commonItem']
    if slot.get('uniqueItem'):
        return slot['uniqueItem']
    for ws in ('set1', 'set2'):
        inner = slot.get(ws) or {}
        item = inner.get('commonItem') or inner.get('uniqueItem')
        if item:
            return item
    return None


def _enumerate_slot(slot):
    """Yield ``(item_dict, runes, anointment, weapon_set_index)`` per item.

    ``weapon_set_index`` is 0 for the primary slot and 1 for a swap slot.
    Non-weapon slots yield once at index 0.
    """
    if not slot:
        return
    if 'set1' in slot or 'set2' in slot:
        for i, ws in enumerate(('set1', 'set2')):
            inner = slot.get(ws) or {}
            item = inner.get('commonItem') or inner.get('uniqueItem')
            if item:
                yield (item, inner.get('runes') or [],
                       inner.get('anointment'), i)
        return
    item = slot.get('commonItem') or slot.get('uniqueItem')
    if item:
        yield item, slot.get('runes') or [], slot.get('anointment'), 0


def _anointment_line(anoint):
    if not anoint:
        return None
    if isinstance(anoint, dict):
        text = (anoint.get('description') or anoint.get('name')
                or anoint.get('slug'))
        if text:
            return f'{text} (enchant)'
    if isinstance(anoint, str):
        return f'{anoint} (enchant)'
    return None


def _item_text(item, runes=(), anointment=None, pob=None):
    """Render a Mobalytics item as Path of Building item text.

    Section dividers (``--------``) and an ``Item Level`` line match the
    structure PoB's Item:ParseRaw expects, which is also what pobb.in's
    renderer reads to display the item list.
    """
    if not item:
        return None
    name = item.get('name') or 'Item'
    rarity = 'UNIQUE' if item.get('isUnique') else 'RARE'
    lines = ['Rarity: ' + rarity, name]
    if rarity == 'UNIQUE':
        base = (pob.unique_bases.get(name.lower()) if pob else None
                or _FALLBACK_UNIQUE_BASES.get(name.lower()))
        lines.append(base or name)
    else:
        lines.append(name)  # Mobalytics reports rares by base type
    lines += ['--------', 'Item Level: 82']
    if runes:
        lines.append('Sockets: ' + ' '.join(['S'] * len(runes)))
        for rune in runes:
            lines.append('Rune: ' + _humanize_rune(rune.get('slug', '')))
    lines.append('--------')
    anoint = _anointment_line(anointment)
    if anoint:
        lines += [anoint, '--------']
    implicits = item.get('implicitDescriptions') or []
    lines.append('Implicits: %d' % len(implicits))
    lines += [d['description'] for d in implicits]
    explicits = [d['description'] for d in (item.get('explicitDescriptions') or [])]
    if explicits:
        if implicits:
            lines.append('--------')
        lines += explicits
    return '\n'.join(lines)


# -- jewels ---------------------------------------------------------------
# Mobalytics jewelSlug -> PoB2 base type name.
# PoE2 uses Ruby/Emerald/Sapphire/Diamond (not the old PoE1 "X Jewel" names).
_JEWEL_BASE_NAMES = {
    'jewel-jewelstr':       'Ruby',
    'jewel-jeweldex':       'Emerald',
    'jewel-jewelint':       'Sapphire',
    'jewel-jewelstrdex':    'Diamond',
    'jewel-jewelstrint':    'Diamond',
    'jewel-jeweldexint':    'Diamond',
    'jewel-jewelnone':      'Diamond',
}


def _jewel_base_name(slug):
    """Map a Mobalytics jewel slug to a human-readable PoB base type."""
    if slug in _JEWEL_BASE_NAMES:
        return _JEWEL_BASE_NAMES[slug]
    return 'Diamond'  # safest PoE2 fallback (generic jewel base)


def _jewel_text(jewel, pob):
    """Render a Mobalytics jewel entry as PoB item text."""
    slug = jewel.get('jewelSlug') or ''
    if jewel.get('isUnique'):
        # Unique jewels: try to derive a readable name from the slug.
        name = (jewel.get('jewelName') or slug).replace('jewel-', '') \
            .replace('_', '-').replace('-', ' ').title() or 'Jewel'
        base = name
        rarity = 'UNIQUE'
    else:
        base = _jewel_base_name(slug)
        name = base
        rarity = 'RARE'
    lines = [
        'Rarity: ' + rarity,
        name,
        base,
        '--------',
        'Item Level: 82',
        '--------',
        'Implicits: 0',
    ]
    return '\n'.join(lines)


def _jewels(variant):
    return (variant.get('passiveTree') or {}).get('jewels') or []


# -- priority list --------------------------------------------------------
def _priority_notes(variant):
    """Return formatted priority info for a variant: ascendancy, equipment, gems.

    Returns an empty string when no useful data is present.
    """
    parts = []

    # Ascendancy node priority
    asc_pl = ((variant.get('passiveTree') or {})
              .get('ascendancyTree') or {}).get('priorityList') or []
    if asc_pl:
        lines = ['Ascendancy Priority:']
        for i, entry in enumerate(asc_pl, 1):
            name = entry.get('name') or entry.get('slug', '')
            lines.append(f'  {i}. {name}')
        parts.append('\n'.join(lines))

    # Equipment priority list
    eq_pl = (variant.get('equipment') or {}).get('priorityList') or []
    if eq_pl:
        lines = ['Equipment Priority:']
        for i, entry in enumerate(eq_pl, 1):
            name = entry.get('name') or entry.get('slug', '')
            slot = entry.get('type', '')
            lines.append(f'  {i}. {name}' + (f' ({slot})' if slot else ''))
        parts.append('\n'.join(lines))

    # Skill gem priority (grouped by parent active skill).
    # Build slug->display-name map from the skillGems.gems list first so we
    # get proper names like "Essence Drain" instead of "essencedrainplayer".
    pg = (variant.get('skillGems') or {}).get('priorityGems') or []
    if pg:
        slug_to_name: dict = {}
        for grp in (variant.get('skillGems') or {}).get('gems', []):
            act = grp.get('activeSkill') or {}
            s = (act.get('gemSlug') or '').lower()
            n = act.get('name') or ''
            if s and n:
                slug_to_name[s] = n
        groups: dict = {}
        for gem in pg:
            parent = (gem.get('parentActiveSkillGemSlug') or '').lower()
            label = slug_to_name.get(parent) or slug_to_name.get(
                re.sub(r'(player.*|two|three|four)$', '', parent))
            if not label:
                # Last-resort: strip suffix + title-case the slug
                label = re.sub(r'(player.*|two|three|four)$', '', parent)
                label = label.strip().title() or 'General'
            gem_name_str = gem.get('name') or gem.get('gemSlug', '')
            groups.setdefault(label, []).append(gem_name_str)
        lines = ['Gem Priorities:']
        for label, names in groups.items():
            lines.append(f'  {label}: {", ".join(names)}')
        parts.append('\n'.join(lines))

    return '\n\n'.join(parts)


# -- XML components -------------------------------------------------------
def _spec_xml(variant, cls_info, tree_version, title=None):
    """Build the <Spec> element including weapon sets, sockets, attribute overrides."""
    attrs = (
        'treeVersion="%s" classId="%d" ascendClassId="%d" '
        'classInternalId="%d" ascendancyInternalId="%s" '
        'secondaryAscendClassId="0" nodes="%s" masteryEffects=""'
    ) % (tree_version, cls_info['class_id'], cls_info['ascend_id'],
         cls_info['class_internal_id'], _esc(cls_info['ascend_internal_id']),
         ','.join(_tree_nodes(variant)))
    if title:
        attrs = 'title="%s" %s' % (_esc(title), attrs)

    children = []
    for set_idx, nodes in _weapon_set_tree_nodes(variant).items():
        children.append(
            '<WeaponSet%d nodes="%s"/>' % (set_idx, ','.join(nodes)))

    # Jewel sockets are populated by the caller (it knows item IDs).
    sockets_xml = variant.get('_jewel_sockets')
    if sockets_xml:
        children.append(sockets_xml)
    else:
        children.append('<Sockets/>')

    overrides = _attribute_overrides(variant)
    children.append(
        '<Overrides><AttributeOverride strNodes="%s" dexNodes="%s" '
        'intNodes="%s"/></Overrides>'
        % (','.join(overrides['str']), ','.join(overrides['dex']),
           ','.join(overrides['int'])))

    return '<Spec %s>\n%s\n</Spec>' % (attrs, '\n'.join(children))


def _skillset_xml(variant, pob, set_id, title=None):
    skills = []
    for grp in _skill_groups(variant):
        gem_xml = []
        for g in grp['gems']:
            nm = g['name'] or gem_name(g['slug'], pob)
            gem_xml.append(
                '<Gem level="20" quality="0" qualityId="Default" enabled="true" '
                'enableGlobal1="true" enableGlobal2="true" nameSpec="%s"/>'
                % _esc(nm))
        skills.append('<Skill mainActiveSkill="1" enabled="true" label="%s">\n%s\n</Skill>'
                       % (_esc(grp['label']), '\n'.join(gem_xml)))
    head = '<SkillSet id="%d"%s>' % (
        set_id, ' title="%s"' % _esc(title) if title else '')
    return head + '\n' + '\n'.join(skills) + '\n</SkillSet>'


def _itemset_xml(variant, pob, set_id, start_item_id, title=None):
    """Render the variant's equipment + jewels.

    Returns ``(item_xml_list, itemset_xml, jewel_sockets_xml, next_item_id)``.
    The jewel-sockets XML is consumed by ``_spec_xml`` for this variant.
    """
    items, slots = [], []
    iid = start_item_id
    equipment = variant.get('equipment') or {}
    has_swap = False

    for moba_slot, pob_slot in _SLOT_MAP.items():
        slot_dict = equipment.get(moba_slot)
        for item, runes, anointment, set_idx in _enumerate_slot(slot_dict):
            txt = _item_text(item, runes=runes, anointment=anointment, pob=pob)
            if not txt:
                continue
            target = pob_slot
            if moba_slot in _WEAPON_SLOTS and set_idx == 1:
                target = pob_slot + ' Swap'
                has_swap = True
            items.append('<Item id="%d">\n%s\n</Item>' % (iid, _esc(txt)))
            slots.append('<Slot name="%s" itemId="%d"/>' % (target, iid))
            iid += 1

    # Jewels: one PoB item per Mobalytics jewel, slotted into <Sockets>.
    jewel_sockets = []
    filled_socket_nodes = set()
    for jewel in _jewels(variant):
        node_ids = _slug_ids([jewel.get('nodeSlug', '')])
        if not node_ids:
            continue
        txt = _jewel_text(jewel, pob)
        items.append('<Item id="%d">\n%s\n</Item>' % (iid, _esc(txt)))
        jewel_sockets.append(
            '<Socket nodeId="%s" itemId="%d"/>' % (node_ids[0], iid))
        filled_socket_nodes.add(node_ids[0])
        iid += 1

    # Emit empty sockets for allocated jewel-socket nodes that have no jewel.
    # PoB2 crashes if a containJewelSocket node is in the tree but has no
    # corresponding <Socket> entry.
    if pob and hasattr(pob, 'jewel_socket_nodes'):
        pob_sockets = pob.jewel_socket_nodes
        for nid in _tree_nodes(variant):
            if nid in pob_sockets and nid not in filled_socket_nodes:
                jewel_sockets.append('<Socket nodeId="%s" itemId="0"/>' % nid)

    jewel_sockets_xml = '<Sockets>%s</Sockets>' % ''.join(jewel_sockets) \
        if jewel_sockets else '<Sockets/>'

    head = '<ItemSet useSecondWeaponSet="%s" id="%d"%s>' % (
        'true' if has_swap else 'false', set_id,
        ' title="%s"' % _esc(title) if title else '')
    itemset_xml = head + '\n' + '\n'.join(slots) + '\n</ItemSet>'
    return items, itemset_xml, jewel_sockets_xml, iid


def _document(cls_info, level, specs, skillsets, all_items, itemsets,
              notes=None):
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<PathOfBuilding2>',
        # targetVersion="0_1" marks this as a Path of Exile 2 build; without
        # it pobb.in / PoB treat the build as legacy PoE1 and the passive
        # tree fails to render.
        '<Build targetVersion="0_1" level="%d" className="%s" ascendClassName="%s" '
        'mainSocketGroup="1" viewMode="TREE">' % (
            level, _esc(cls_info['class_name']),
            _esc(cls_info['ascend_name'])),
        # A child element is required for stricter parsers (e.g. pobb.in);
        # Path of Building recalculates all stats on import regardless.
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
    parts += ['<Config/>', '</PathOfBuilding2>']
    return '\n'.join(parts)


def encode(xml):
    """Encode build XML as a Path of Building import code."""
    return base64.b64encode(zlib.compress(xml.encode('utf-8'), 9)).decode('ascii')


# -- public API -----------------------------------------------------------
def _resolve(variant, pob, class_override, ascendancy_override):
    ascendancy = ascendancy_override or detect_ascendancy(variant, pob)
    info = resolve_class(class_override, ascendancy)
    info['detected'] = bool(ascendancy and not ascendancy_override)
    return info


def _build_variant_parts(variant, pob, info, set_id, start_item_id,
                          tree_version, title):
    """Build skillset/itemset/items/spec for one variant (shared by convert and
    convert_merged). Returns dict with the four XML fragments + next id."""
    skillset = _skillset_xml(variant, pob, set_id, title)
    items, itemset, sockets_xml, next_id = _itemset_xml(
        variant, pob, set_id, start_item_id, title)
    # Stash sockets so _spec_xml can render them with the correct item IDs.
    variant['_jewel_sockets'] = sockets_xml
    try:
        spec = _spec_xml(variant, info, tree_version, title)
    finally:
        variant.pop('_jewel_sockets', None)
    return {
        'spec': spec, 'skillset': skillset, 'items': items,
        'itemset': itemset, 'next_id': next_id,
    }


def convert(variant, pob=None, class_override=None,
            ascendancy_override=None, level=90, title=None, notes=None):
    """Convert one build variant into a standalone build code."""
    info = _resolve(variant, pob, class_override, ascendancy_override)
    tree_version = pob.tree_version if pob else '0_4'
    parts = _build_variant_parts(
        variant, pob, info, set_id=1, start_item_id=1,
        tree_version=tree_version, title=title)
    full_notes = '\n\n'.join(filter(None, [notes, _priority_notes(variant)]))
    xml = _document(info, level, [parts['spec']], [parts['skillset']],
                    parts['items'], [parts['itemset']],
                    notes=full_notes or None)
    return {
        'code': encode(xml),
        'xml': xml,
        'class': info['class_name'],
        'ascendancy': info['ascend_name'],
        'tree_version': tree_version,
        'node_count': len(_tree_nodes(variant)),
        'skill_count': len(_skill_groups(variant)),
        'detected_ascendancy': info['detected'],
    }


def convert_merged(variants, pob=None, class_override=None,
                    ascendancy_override=None, level=90, titles=None,
                    progression_order=True, notes=None):
    """Merge several variants into one build with switchable specs/sets.

    Each variant becomes a Tree spec, a Skill Set, and an Item Set, all
    selectable from the dropdowns inside Path of Building.

    With ``progression_order`` (default), variants are sorted ascending by
    main-tree node count so leveling variants come before endgame ones.
    """
    if not variants:
        raise ValueError("no variants to merge")
    titles = titles or [f'Variant {i}' for i in range(len(variants))]
    if progression_order:
        order = sorted(range(len(variants)),
                       key=lambda i: len((variants[i].get('passiveTree') or {})
                                          .get('mainTree', {})
                                          .get('selectedSlugs', [])))
        variants = [variants[i] for i in order]
        titles = [titles[i] for i in order]

    # Find class info from the first variant that has detectable ascendancy;
    # fall back to each subsequent variant so sparse leveling variants don't
    # block the whole merge.
    head = None
    for v in variants:
        try:
            head = _resolve(v, pob, class_override, ascendancy_override)
            break
        except ValueError:
            continue
    if head is None:
        # All variants failed - raise from the first one for a clear message.
        head = _resolve(variants[0], pob, class_override, ascendancy_override)
    tree_version = pob.tree_version if pob else '0_4'

    specs, skillsets, all_items, itemsets = [], [], [], []
    next_id = 1
    for i, variant in enumerate(variants):
        try:
            info = _resolve(variant, pob, class_override, ascendancy_override)
        except ValueError:
            info = head  # sparse variant - reuse detected class
        parts = _build_variant_parts(
            variant, pob, info, set_id=i + 1, start_item_id=next_id,
            tree_version=tree_version, title=titles[i])
        specs.append(parts['spec'])
        skillsets.append(parts['skillset'])
        all_items += parts['items']
        itemsets.append(parts['itemset'])
        next_id = parts['next_id']

    priority_parts = []
    for title_str, variant in zip(titles, variants):
        p = _priority_notes(variant)
        if p:
            priority_parts.append(f'=== {title_str} ===\n{p}')
    full_notes = '\n\n'.join(filter(None, [notes] + priority_parts))
    xml = _document(head, level, specs, skillsets, all_items, itemsets,
                    notes=full_notes or None)
    return {
        'code': encode(xml),
        'xml': xml,
        'class': head['class_name'],
        'ascendancy': head['ascend_name'],
        'tree_version': tree_version,
        'variant_count': len(variants),
        'node_count': sum(len(_tree_nodes(v)) for v in variants),
        'detected_ascendancy': head['detected'],
    }
