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
        },
        'passiveTree': {
            'mainTree': {'selectedSlugs': ['node-12345']},
            'ascendancyTree': {
                'selectedSlugs': ['node-23710', 'node-33141'],  # Lich nodes
                'priorityList': [],
            },
        },
        'atlasTree': None,
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
