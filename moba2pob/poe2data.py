"""Static Path of Exile 2 class data.

Extracted from Path of Building Community (PoE2) tree.lua. These are stable
game constants; bundling them lets the converter resolve class / ascendancy
IDs without a Path of Building install.
"""

# className -> {classId, ascendancies (ordered)}.
# classId is the Spec classId; ascendClassId is the 1-based index of an
# ascendancy in the list below (0 = no ascendancy).
CLASSES = {
    'Ranger':    {'classId': 1, 'ascendancies': ['Deadeye', 'Pathfinder']},
    'Huntress':  {'classId': 2, 'ascendancies': ['Amazon', 'Ritualist']},
    'Warrior':   {'classId': 3, 'ascendancies': ['Titan', 'Warbringer', 'Smith of Kitava']},
    'Mercenary': {'classId': 4, 'ascendancies': ['Tactician', 'Witchhunter', 'Gemling Legionnaire']},
    'Druid':     {'classId': 5, 'ascendancies': ['Oracle', 'Shaman']},
    'Witch':     {'classId': 6, 'ascendancies': ['Infernalist', 'Blood Mage', 'Lich', 'Abyssal Lich']},
    'Sorceress': {'classId': 7, 'ascendancies': ['Stormweaver', 'Chronomancer', 'Disciple of Varashta']},
    'Monk':      {'classId': 8, 'ascendancies': ['Invoker', 'Acolyte of Chayula']},
}

# ascendancyName -> className
ASCENDANCY_TO_CLASS = {
    asc: cls for cls, info in CLASSES.items() for asc in info['ascendancies']
}


def resolve_class(class_name=None, ascendancy=None):
    """Return (className, classId, ascendClassId) from a class and/or ascendancy.

    Either argument may be given; ascendancy alone is enough to infer the class.
    Raises ValueError if nothing resolvable is supplied.
    """
    if ascendancy:
        ascendancy = _match(ascendancy, ASCENDANCY_TO_CLASS)
        class_name = ASCENDANCY_TO_CLASS[ascendancy]
    if not class_name:
        raise ValueError("class could not be determined; pass --class/--ascendancy")
    class_name = _match(class_name, CLASSES)
    info = CLASSES[class_name]
    ascend_id = 0
    if ascendancy:
        ascend_id = info['ascendancies'].index(ascendancy) + 1
    return class_name, info['classId'], ascend_id


def _match(value, table):
    """Case-insensitive key lookup."""
    for key in table:
        if key.lower() == value.strip().lower():
            return key
    raise ValueError(f"unknown name {value!r} (have: {', '.join(table)})")
