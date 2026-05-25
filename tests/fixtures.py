"""Test fixtures: a minimal Mobalytics-shaped build variant and page."""


def sample_variant():
    """Return a minimal but complete Mobalytics variant dict.

    Includes one passive node, one ascendancy node (Lich), one skill group,
    one rare item, and one unique item, so the converter exercises every
    item rarity branch and the ascendancy detector has data to work with.
    """
    return {
        'id': 'sample-id',
        'genericBuilder': {'slots': None},
        'equipment': {
            'priorityList': [
                {'name': 'Withered Wand', 'type': 'mainHand',
                 'slug': 'weapon-wand', 'description': None, 'notes': None},
                {'name': "Atziri's Disdain", 'type': 'helmet',
                 'slug': 'unique-helmet', 'description': None, 'notes': None},
            ],
            'mainHand': {
                'set1': {
                    'commonItem': {
                        'slug': 'weapon-wand',
                        'isUnique': False,
                        'name': 'Withered Wand',
                        'itemClassSlug': 'wand',
                        'explicitDescriptions': [
                            {'description': '50% increased Spell Damage'},
                        ],
                    },
                },
            },
            'helmet': {
                'commonItem': {
                    'slug': 'unique-helmet',
                    'isUnique': True,
                    'name': 'Atziri\'s Disdain',
                    'itemClassSlug': 'helmet',
                    'explicitDescriptions': [
                        {'description': '+30 to all Attributes'},
                    ],
                },
            },
        },
        'skillGems': {
            'gems': [
                {
                    'activeSkill': {
                        'gemSlug': 'contagionplayer',
                        'name': 'Contagion',
                    },
                    'subSkills': [
                        {'gemSlug': 'supportunleashplayer'},
                    ],
                },
            ],
            'priorityGems': [
                {
                    'gemSlug': 'supportunleashplayer',
                    'name': 'Unleash',
                    'gemType': 'SUPPORT',
                    'description': None,
                    'parentActiveSkillGemSlug': 'contagionplayer',
                },
            ],
        },
        'passiveTree': {
            'mainTree': {'selectedSlugs': ['node-12345']},
            'ascendancyTree': {
                'selectedSlugs': ['node-23710', 'node-33141'],  # Lich nodes
                'priorityList': [
                    {'slug': 'node-23710', 'name': 'Soulless Form',
                     'type': 'ASCENDANCY_LARGE'},
                    {'slug': 'node-33141', 'name': 'Eternal Life',
                     'type': 'ASCENDANCY_LARGE'},
                ],
            },
            'jewels': [
                {
                    'isUnique': False,
                    'jewelSlug': 'jewel-jewelint',
                    'nodeSlug': 'node-7960',
                    'prefixSlugs': ['IncreasedEnergyShieldPercent2'],
                    'suffixSlugs': ['JewelManaRegeneration'],
                },
            ],
        },
        'atlasTree': None,
    }


def sample_maxroll_planner():
    """Return a minimal Maxroll planner dict with two phases.

    Phase 0 = leveling (3 nodes), Phase 1 = endgame (5 nodes).
    Includes items with explicits/implicits, a unique item, a magic item,
    jewels in tree sockets, and skill gems.
    """
    return {
        'ascendancy': 'Witch3',  # internal ID for Lich
        'passives': {
            'variants': [
                {
                    'name': 'Leveling',
                    'history': [100, 200, 300],
                    'jewels': {},
                },
                {
                    'name': 'Endgame',
                    'history': [100, 200, 300, 400, 500,
                                {'id': 600, 'set': 2}],
                    'jewels': {'7960': 10},
                },
            ],
        },
        'equipment': {
            'variants': [
                {
                    'name': 'Leveling',
                    'items': {'Weapon': 1, 'Helm': 2},
                },
                {
                    'name': 'Endgame',
                    'items': {'Weapon': 1, 'Helm': 2, 'BodyArmour': 3,
                              'Amulet': 4, 'Ring': 5},
                },
            ],
        },
        'skills': {
            'steps': [
                {
                    'name': 'Leveling',
                    'skills': [
                        {'gems': [
                            {'id': 'Metadata/Items/Gems/SkillGemContagion',
                             'level': 1},
                            {'id': 'Metadata/Items/Gems/SupportGemUnleash',
                             'level': 1},
                        ]},
                    ],
                },
                {
                    'name': 'Endgame',
                    'skills': [
                        {'gems': [
                            {'id': 'Metadata/Items/Gems/SkillGemContagion',
                             'level': 20},
                            {'id': 'Metadata/Items/Gems/SupportGemUnleash',
                             'level': 20},
                        ]},
                    ],
                },
            ],
        },
        'items': {
            '1': {
                'name': 'Plague Wand',
                'ilvl': 82,
                'rarity': 'rare',
                'base': 'Metadata/Items/Weapons/OneHandWeapons/Wands/FourWandInt',
                'sockets': [],
                'stats': {'implicit': {}, 'explicit': {'base_maximum_mana': 50,
                                                        'additional_intelligence': 30},
                          'enchant': {}, 'rune': {}},
                'mods': {'implicit': {},
                         'explicit': {'IncreasedMana4': {'base_maximum_mana': 50},
                                      'Intelligence4': {'additional_intelligence': 30}},
                         'enchant': {}},
            },
            '2': {
                'name': "Atziri's Disdain",
                'ilvl': 82,
                'rarity': 'unique',
                'base': 'Metadata/Items/Armours/Helmets/FourHelmetInt',
                'sockets': [],
                'stats': {'implicit': {}, 'explicit': {}, 'enchant': {}, 'rune': {}},
                'mods': {'implicit': {}, 'explicit': {}, 'enchant': {}},
            },
            '3': {
                'name': 'Tabula Rasa',
                'ilvl': 82,
                'rarity': 'unique',
                'base': 'Metadata/Items/Armours/BodyArmours/FourBodyInt',
                'sockets': [],
                'stats': {'implicit': {}, 'explicit': {}, 'enchant': {}, 'rune': {}},
                'mods': {'implicit': {}, 'explicit': {}, 'enchant': {}},
            },
            '4': {
                'name': 'Rare Amulet',
                'ilvl': 82,
                'rarity': 'magic',
                'base': 'Metadata/Items/Amulets/FourAmuletInt',
                'sockets': [],
                'stats': {'implicit': {}, 'explicit': {}, 'enchant': {}, 'rune': {}},
                'mods': {'implicit': {}, 'explicit': {}, 'enchant': {}},
            },
            '5': {
                'name': 'Circle Ring',
                'ilvl': 82,
                'rarity': 'rare',
                'base': 'Metadata/Items/Rings/FourRing',
                'sockets': [],
                'stats': {'implicit': {}, 'explicit': {'base_maximum_life': 15},
                          'enchant': {}, 'rune': {}},
                'mods': {'implicit': {},
                         'explicit': {'IncreasedLife2': {'base_maximum_life': 15}},
                         'enchant': {}},
            },
            '10': {
                'name': 'Rare Jewel',
                'ilvl': 82,
                'rarity': 'rare',
                'base': 'Metadata/Items/Jewels/JewelInt',
                'sockets': [],
                'stats': {'implicit': {}, 'explicit': {'maximum_life_+%': 5},
                          'enchant': {}, 'rune': {}},
                'mods': {'implicit': {},
                         'explicit': {'IncreasedLifePercent1': {'maximum_life_+%': 5}},
                         'enchant': {}},
            },
        },
    }


def sample_html():
    """Return HTML resembling a Mobalytics build page, small but realistic."""
    state = (
        '{"poe2State":{"apollo":{"graphqlV2":{"queries":[{},'
        '{"state":{"data":[{"game":{"documents":'
        '{"userGeneratedDocumentBySlug":{"data":{"data":'
        '{"name":"Sample Build",'
        '"buildVariants":{"values":[{"id":"var-a","name":null}]},'
        '"pobCode":null,"lootFilter":null}}}}}}]}}]}}}}'
    )
    return (
        '<html><body>'
        '<button data-key="var-a" role="tab">'
        '<div>Endgame</div><div>some other text</div>'
        '</button>'
        '<script>window.__PRELOADED_STATE__=' + state + ';</script>'
        '</body></html>'
    )
