"""Static Path of Exile 2 class data.

Extracted from Path of Building Community (PoE2) tree.lua. These are stable
game constants; bundling them lets the converter resolve class / ascendancy
IDs without a Path of Building install.

Path of Building (and pobb.in) read two parallel identifiers for the class:

* ``classId``         - the index into the tree's classes table.
* ``classInternalId`` - the integerId set by GGG.

Likewise for ascendancies it reads both ``ascendClassId`` (position in the
class's ascendancy list) and ``ascendancyInternalId`` (a GGG-side string like
``Witch3``). Omitting the internal IDs makes pobb.in misidentify the build as
PoE1 and fail to render the passive tree.
"""

# className -> {classId, integerId, ascendancies: [{name, internalId}]}
CLASSES = {
    'Ranger': {
        'classId': 1, 'integerId': 2,
        'ascendancies': [
            {'name': 'Deadeye',    'internalId': 'Ranger1'},
            {'name': 'Pathfinder', 'internalId': 'Ranger3'},
        ],
    },
    'Huntress': {
        'classId': 2, 'integerId': 8,
        'ascendancies': [
            {'name': 'Amazon',        'internalId': 'Huntress1'},
            {'name': 'Spirit Walker', 'internalId': 'Huntress2'},
            {'name': 'Ritualist',     'internalId': 'Huntress3'},
        ],
    },
    'Warrior': {
        'classId': 3, 'integerId': 6,
        'ascendancies': [
            {'name': 'Titan',           'internalId': 'Warrior1'},
            {'name': 'Warbringer',      'internalId': 'Warrior2'},
            {'name': 'Smith of Kitava', 'internalId': 'Warrior3'},
        ],
    },
    'Mercenary': {
        'classId': 4, 'integerId': 9,
        'ascendancies': [
            {'name': 'Tactician',           'internalId': 'Mercenary1'},
            {'name': 'Witchhunter',         'internalId': 'Mercenary2'},
            {'name': 'Gemling Legionnaire', 'internalId': 'Mercenary3'},
        ],
    },
    'Druid': {
        'classId': 5, 'integerId': 11,
        'ascendancies': [
            {'name': 'Oracle', 'internalId': 'Druid1'},
            {'name': 'Shaman', 'internalId': 'Druid2'},
        ],
    },
    'Witch': {
        'classId': 6, 'integerId': 1,
        'ascendancies': [
            {'name': 'Infernalist',  'internalId': 'Witch1'},
            {'name': 'Blood Mage',   'internalId': 'Witch2'},
            {'name': 'Lich',         'internalId': 'Witch3'},
            {'name': 'Abyssal Lich', 'internalId': 'Witch3b'},
        ],
    },
    'Sorceress': {
        'classId': 7, 'integerId': 7,
        'ascendancies': [
            {'name': 'Stormweaver',          'internalId': 'Sorceress1'},
            {'name': 'Chronomancer',         'internalId': 'Sorceress2'},
            {'name': 'Disciple of Varashta', 'internalId': 'Sorceress3'},
        ],
    },
    'Monk': {
        'classId': 8, 'integerId': 10,
        'ascendancies': [
            {'name': 'Martial Artist',     'internalId': 'Monk1'},
            {'name': 'Invoker',            'internalId': 'Monk2'},
            {'name': 'Acolyte of Chayula', 'internalId': 'Monk3'},
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
    """Return a dict of every identifier PoB needs for a class+ascendancy."""
    if ascendancy:
        try:
            ascendancy = _match(ascendancy, ASCENDANCY_TO_CLASS)
            class_name = ASCENDANCY_TO_CLASS[ascendancy]
        except ValueError:
            # Ascendancy not in the bundled PoB data yet (e.g. a brand-new
            # league ascendancy like Martial Artist). Fall back to no
            # ascendancy if the class is otherwise known, rather than failing
            # the whole import.
            if not class_name:
                raise
            ascendancy = None
    if not class_name:
        raise ValueError("class could not be determined; pass --class/--ascendancy")
    class_name = _match(class_name, CLASSES)
    info = CLASSES[class_name]
    ascend_id = 0
    ascend_internal = ''
    ascend_name = 'None'
    if ascendancy:
        for i, a in enumerate(info['ascendancies'], start=1):
            if a['name'] == ascendancy:
                ascend_id = i
                ascend_internal = a['internalId']
                ascend_name = a['name']
                break
    return {
        'class_name': class_name,
        'class_id': info['classId'],
        'class_internal_id': info['integerId'],
        'ascend_id': ascend_id,
        'ascend_internal_id': ascend_internal,
        'ascend_name': ascend_name,
    }


def _match(value, table):
    for key in table:
        if key.lower() == value.strip().lower():
            return key
    raise ValueError(f"unknown name {value!r} (have: {', '.join(table)})")
