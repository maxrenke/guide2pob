"""Static Path of Exile 1 class data.

Extracted from the decoded pobCode XML (className="Witch" classId="3",
ascendClassName="Elementalist" ascendClassId="2") and cross-referenced
with Path of Building Community (PoE1) tree ordering.

PoE1 class IDs follow the passive-tree starting-position order:
  0 = Scion (center), 1 = Marauder, 2 = Ranger, 3 = Witch,
  4 = Duelist, 5 = Templar, 6 = Shadow

Ascendancy IDs are 1-indexed per class.

Unlike PoE2, PoB1 does not use classInternalId / ascendancyInternalId
in the Spec element - only classId and ascendClassId are needed.
"""

# className -> {classId, ascendancies: [{name, ascendId}]}
CLASSES = {
    'Scion': {
        'classId': 0,
        'ascendancies': [
            {'name': 'Ascendant', 'ascendId': 1},
        ],
    },
    'Marauder': {
        'classId': 1,
        'ascendancies': [
            {'name': 'Juggernaut', 'ascendId': 1},
            {'name': 'Berserker',  'ascendId': 2},
            {'name': 'Chieftain', 'ascendId': 3},
        ],
    },
    'Ranger': {
        'classId': 2,
        'ascendancies': [
            {'name': 'Deadeye',    'ascendId': 1},
            {'name': 'Raider',     'ascendId': 2},
            {'name': 'Pathfinder', 'ascendId': 3},
        ],
    },
    'Witch': {
        'classId': 3,
        'ascendancies': [
            {'name': 'Necromancer',  'ascendId': 1},
            {'name': 'Elementalist', 'ascendId': 2},
            {'name': 'Occultist',    'ascendId': 3},
        ],
    },
    'Duelist': {
        'classId': 4,
        'ascendancies': [
            {'name': 'Slayer',    'ascendId': 1},
            {'name': 'Gladiator', 'ascendId': 2},
            {'name': 'Champion',  'ascendId': 3},
        ],
    },
    'Templar': {
        'classId': 5,
        'ascendancies': [
            {'name': 'Inquisitor',  'ascendId': 1},
            {'name': 'Hierophant', 'ascendId': 2},
            {'name': 'Guardian',   'ascendId': 3},
        ],
    },
    'Shadow': {
        'classId': 6,
        'ascendancies': [
            {'name': 'Assassin',  'ascendId': 1},
            {'name': 'Saboteur',  'ascendId': 2},
            {'name': 'Trickster', 'ascendId': 3},
        ],
    },
}

# ascendancyName -> className
ASCENDANCY_TO_CLASS = {
    a['name']: cls
    for cls, info in CLASSES.items()
    for a in info['ascendancies']
}


def resolve_class(class_name=None, ascendancy=None):
    """Return a dict of PoB identifiers for a class+ascendancy pair."""
    if ascendancy:
        ascendancy = _match(ascendancy, ASCENDANCY_TO_CLASS)
        class_name = ASCENDANCY_TO_CLASS[ascendancy]
    if not class_name:
        raise ValueError(
            "class could not be determined; pass --class / --ascendancy")
    class_name = _match(class_name, CLASSES)
    info = CLASSES[class_name]
    ascend_id = 0
    ascend_name = 'None'
    if ascendancy:
        for a in info['ascendancies']:
            if a['name'] == ascendancy:
                ascend_id = a['ascendId']
                ascend_name = a['name']
                break
    return {
        'class_name': class_name,
        'class_id': info['classId'],
        'ascend_id': ascend_id,
        'ascend_name': ascend_name,
    }


def _match(value, table):
    for key in table:
        if key.lower() == value.strip().lower():
            return key
    raise ValueError(
        "unknown name %r (have: %s)" % (value, ', '.join(table)))
