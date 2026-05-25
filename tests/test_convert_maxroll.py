import re
import unittest

from guide2pob.convert_maxroll import (
    convert, convert_merged,
    _parse_history, _gem_name, _item_text, _base_type_from_path,
    _itemset_xml_maxroll, _skillset_xml_maxroll,
)
from tests.fixtures import sample_maxroll_planner

_PROFILE = {'name': 'Test Build', 'ascendancy': 'Witch3'}


class TestParseHistory(unittest.TestCase):

    def test_plain_ints_go_to_set1(self):
        set1, set2 = _parse_history([100, 200, 300])
        self.assertEqual(set1, ['100', '200', '300'])
        self.assertEqual(set2, [])

    def test_dict_with_set2_goes_to_set2(self):
        set1, set2 = _parse_history([
            100,
            {'id': 200, 'set': 2},
            {'id': 300, 'set': 1},
        ])
        self.assertEqual(set1, ['100', '300'])
        self.assertEqual(set2, ['200'])

    def test_empty_history(self):
        self.assertEqual(_parse_history([]), ([], []))
        self.assertEqual(_parse_history(None), ([], []))


class TestGemName(unittest.TestCase):

    def test_camelcase_split_no_pob(self):
        name = _gem_name('Metadata/Items/Gems/SkillGemContagion', pob=None)
        self.assertEqual(name, 'Contagion')

    def test_support_gem_no_pob(self):
        name = _gem_name('Metadata/Items/Gems/SupportGemUnleash', pob=None)
        self.assertEqual(name, 'Unleash')

    def test_tiered_suffix_stripped(self):
        name = _gem_name('Metadata/Items/Gems/SkillGemFireballTwo', pob=None)
        self.assertEqual(name, 'Fireball')

    def test_empty_id(self):
        self.assertEqual(_gem_name('', pob=None), '')


class TestBaseTypeFromPath(unittest.TestCase):

    def test_helmet_int(self):
        self.assertEqual(
            _base_type_from_path('Metadata/Items/Armours/Helmets/FourHelmetInt'),
            'Ancestral Tiara')

    def test_body_str(self):
        self.assertEqual(
            _base_type_from_path('Metadata/Items/Armours/BodyArmours/FourBodyStr'),
            'Warlord Cuirass')

    def test_jewel_int(self):
        self.assertEqual(
            _base_type_from_path('Metadata/Items/Jewels/JewelInt'),
            'Sapphire')

    def test_unknown_returns_none(self):
        self.assertIsNone(_base_type_from_path('Metadata/Items/Unknown/Blob'))


class _FakePobMods:
    """Minimal PoBData stub that provides mod_texts for unit tests."""
    jewel_socket_nodes = {'7960'}
    tree_version = '0_4'
    gems = {}
    unique_bases = {}
    mod_texts = {
        'IncreasedMana4':     '+(35-54) to maximum Mana',
        'Intelligence4':      '+(17-20) to Intelligence',
        'IncreasedLife2':     '+(11-19) to maximum Life',
        'IncreasedLifePercent1': '(5-8)% increased maximum Life',
        'FakeImplicit1':      '(10-15)% increased Cast Speed',
        'FakeRune1':          '+{v}% to Fire Resistance',
    }


class TestItemText(unittest.TestCase):

    def test_rare_item_with_mods(self):
        item = {
            'name': 'Plague Wand',
            'ilvl': 82,
            'rarity': 'rare',
            'base': 'Metadata/Items/Weapons/OneHandWeapons/Wands/FourWandInt',
            'sockets': [],
            'stats': {'implicit': {}, 'explicit': {}, 'enchant': {}, 'rune': {}},
            'mods': {
                'implicit': {'FakeImplicit1': {'cast_speed_+%': 12}},
                'explicit': {'IncreasedMana4': {'base_maximum_mana': 50}},
                'enchant': {},
            },
        }
        pob = _FakePobMods()
        text = _item_text(item, pob=pob)
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: RARE')
        self.assertIn('Implicits: 1', lines)
        self.assertIn('12% increased Cast Speed', lines)
        self.assertIn('+50 to maximum Mana', lines)

    def test_enchant_placed_before_implicits(self):
        item = {
            'name': 'Anoint Amulet',
            'ilvl': 82,
            'rarity': 'rare',
            'base': 'Metadata/Items/Amulets/FourAmuletInt',
            'sockets': [],
            'stats': {'implicit': {}, 'explicit': {}, 'enchant': {}, 'rune': {}},
            'mods': {
                'implicit': {'IncreasedMana4': {'base_maximum_mana': 50}},
                'explicit': {'IncreasedLife2': {'base_maximum_life': 15}},
                'enchant': {'FakeImplicit1': {'cast_speed_+%': 12}},
            },
        }
        pob = _FakePobMods()
        text = _item_text(item, pob=pob)
        lines = text.split('\n')
        # Enchant must appear before Implicits: N
        enchant_idx = next(i for i, l in enumerate(lines) if '12% increased Cast Speed' in l)
        implicit_header_idx = next(i for i, l in enumerate(lines) if l.startswith('Implicits:'))
        self.assertLess(enchant_idx, implicit_header_idx)
        # Implicit count should not include the enchant
        self.assertIn('Implicits: 1', lines)

    def test_unique_item_uses_fallback_base(self):
        item = {
            'name': 'Tabula Rasa',
            'ilvl': 82,
            'rarity': 'unique',
            'base': 'Metadata/Items/Armours/BodyArmours/FourBodyInt',
            'sockets': [],
            'stats': {'implicit': {}, 'explicit': {}, 'enchant': {}, 'rune': {}},
            'mods': {'implicit': {}, 'explicit': {}, 'enchant': {}},
        }
        text = _item_text(item, pob=None)
        self.assertIn('Rarity: UNIQUE', text)
        self.assertIn('Simple Robe', text)

    def test_magic_item_rarity(self):
        item = {
            'name': '',
            'ilvl': 82,
            'rarity': 'magic',
            'base': 'Metadata/Items/Amulets/FourAmuletInt',
            'sockets': [],
            'stats': {'implicit': {}, 'explicit': {}, 'enchant': {}, 'rune': {}},
            'mods': {'implicit': {}, 'explicit': {}, 'enchant': {}},
        }
        text = _item_text(item, pob=None)
        self.assertIn('Rarity: MAGIC', text)

    def test_rune_stats_appended(self):
        item = {
            'name': 'Helm',
            'ilvl': 100,
            'rarity': 'rare',
            'base': 'Metadata/Items/Armours/Helmets/FourHelmetInt',
            'sockets': ['Metadata/Items/SoulCores/RuneFireGreater'],
            'stats': {'implicit': {}, 'explicit': {},
                      'enchant': {}, 'rune': {'base_fire_damage_resistance_%': 14}},
            'mods': {'implicit': {}, 'explicit': {}, 'enchant': {}},
        }
        text = _item_text(item, pob=None)
        self.assertIn('+14% to Fire Resistance', text)
        self.assertIn('Sockets: S', text)

    def test_ilvl_used_from_item(self):
        item = {'name': 'Test', 'ilvl': 95, 'rarity': 'rare',
                'base': 'Metadata/Items/Armours/Helmets/FourHelmetInt',
                'sockets': [],
                'stats': {'implicit': {}, 'explicit': {}, 'enchant': {}, 'rune': {}},
                'mods': {'implicit': {}, 'explicit': {}, 'enchant': {}}}
        text = _item_text(item, pob=None)
        self.assertIn('Item Level: 95', text)

    def test_no_mods_gives_implicits_zero(self):
        item = {'name': 'Empty Helm', 'rarity': 'rare',
                'base': 'Metadata/Items/Armours/Helmets/FourHelmetInt'}
        text = _item_text(item, pob=None)
        self.assertIn('Implicits: 0', text)

    def test_none_returns_none(self):
        self.assertIsNone(_item_text(None, pob=None))

    def test_unique_no_base_path_falls_back(self):
        # Unique with no recognisable base path falls back to 'Item'
        item = {'name': '', 'rarity': 'unique', 'base': ''}
        text = _item_text(item, pob=None)
        # Should produce something (base 'Item' as fallback) - not None
        self.assertIsNotNone(text)
        self.assertIn('Rarity: UNIQUE', text)

    def test_updated_unique_bases(self):
        # Verify corrected PoE2 base types match PoB2's actual data.
        for name, expected_base in [
            ("Atziri's Disdain",  "Gold Circlet"),
            ("Doedre's Tenure",   "Stitched Gloves"),
            ("Snakepit",          "Pearl Ring"),
            ("Headhunter",        "Heavy Belt"),
            ("The Fall of the Axe", "Silver Charm"),
            ("Rite of Passage",   "Golden Charm"),
            ("Bushwhack",         "Lizardscale Boots"),
            ("Effigy of Cruelty", "Antler Focus"),
            ("Beira's Anguish",   "Dousing Charm"),
        ]:
            item = {'name': name, 'rarity': 'unique', 'base': ''}
            text = _item_text(item, pob=None)
            self.assertIsNotNone(text, f'{name} should not return None')
            lines = text.split('\n')
            self.assertEqual(lines[2], expected_base,
                             f'{name}: expected base {expected_base!r}, got {lines[2]!r}')


class TestConvertSingle(unittest.TestCase):

    def setUp(self):
        self.planner = sample_maxroll_planner()
        self.pob = _FakePobMods()
        self.meta = convert(self.planner, _PROFILE, variant_idx=1, level=90,
                            pob=self.pob)

    def test_returns_code_and_xml(self):
        self.assertIn('code', self.meta)
        self.assertIn('xml', self.meta)
        self.assertIn('<PathOfBuilding2>', self.meta['xml'])

    def test_target_version_marks_poe2(self):
        self.assertIn('targetVersion="0_1"', self.meta['xml'])

    def test_class_resolved(self):
        self.assertEqual(self.meta['class'], 'Witch')
        self.assertEqual(self.meta['ascendancy'], 'Lich')

    def test_passive_nodes_in_spec(self):
        # set1 nodes: 100,200,300,400,500
        m = re.search(r'<Spec [^>]+nodes="([^"]+)"', self.meta['xml'])
        self.assertIsNotNone(m)
        nodes = m.group(1).split(',')
        self.assertIn('100', nodes)
        self.assertIn('500', nodes)

    def test_weapon_set2_nodes_in_spec(self):
        self.assertIn('<WeaponSet2 nodes="600"/>', self.meta['xml'])

    def test_items_in_xml(self):
        self.assertIn('Plague Wand', self.meta['xml'])
        self.assertIn('+50 to maximum Mana', self.meta['xml'])

    def test_unique_item_in_xml(self):
        # Apostrophe is HTML-escaped in the XML wrapper
        self.assertIn("Atziri&#x27;s Disdain", self.meta['xml'])

    def test_jewel_socket_emitted(self):
        # endgame phase has a jewel at node 7960
        self.assertIn('<Socket nodeId="7960"', self.meta['xml'])

    def test_skill_group_emitted(self):
        self.assertIn('<Skill ', self.meta['xml'])
        self.assertIn('Contagion', self.meta['xml'])

    def test_node_count_metadata(self):
        # set1 has 5 nodes
        self.assertEqual(self.meta['node_count'], 5)

    def test_skill_count_metadata(self):
        self.assertEqual(self.meta['skill_count'], 1)


class TestConvertMerged(unittest.TestCase):

    def test_two_phases_produce_two_specs(self):
        planner = sample_maxroll_planner()
        meta = convert_merged(planner, _PROFILE)
        specs = re.findall(r'<Spec [^>]+>', meta['xml'])
        self.assertEqual(len(specs), 2)

    def test_progression_order_sorts_leveling_first(self):
        planner = sample_maxroll_planner()
        # Phase 0 has 3 nodes, Phase 1 has 5 - leveling first
        meta = convert_merged(planner, _PROFILE, progression_order=True)
        titles = re.findall(r'<Spec title="([^"]+)"', meta['xml'])
        self.assertEqual(titles[0], 'Leveling')
        self.assertEqual(titles[1], 'Endgame')

    def test_no_reorder_keeps_source_order(self):
        # Reverse planner so endgame is first
        planner = sample_maxroll_planner()
        pvars = planner['passives']['variants']
        pvars[0], pvars[1] = pvars[1], pvars[0]
        evars = planner['equipment']['variants']
        evars[0], evars[1] = evars[1], evars[0]
        ssteps = planner['skills']['steps']
        ssteps[0], ssteps[1] = ssteps[1], ssteps[0]
        meta = convert_merged(planner, _PROFILE, progression_order=False)
        titles = re.findall(r'<Spec title="([^"]+)"', meta['xml'])
        # With no reorder, Endgame should be first (we swapped it)
        self.assertEqual(titles[0], 'Endgame')

    def test_variant_count_in_metadata(self):
        planner = sample_maxroll_planner()
        meta = convert_merged(planner, _PROFILE)
        self.assertEqual(meta['variant_count'], 2)

    def test_notes_included(self):
        planner = sample_maxroll_planner()
        meta = convert_merged(planner, _PROFILE, notes='My notes')
        self.assertIn('<Notes>', meta['xml'])
        self.assertIn('My notes', meta['xml'])


class TestEmptyJewelSocket(unittest.TestCase):

    class _FakePob:
        jewel_socket_nodes = {'7960'}
        tree_version = '0_4'
        gems = {}
        unique_bases = {}
        mod_texts = {}

    def test_empty_socket_for_node_with_no_jewel(self):
        equip = {'items': {}}
        items_dict = {}
        pob = self._FakePob()
        # tree has node 7960 (a socket) but jewels_dict is empty
        _, _, jewel_xml, _ = _itemset_xml_maxroll(
            equip, items_dict, pob, set_id=1, start_item_id=1,
            jewels_dict={}, tree_nodes=['7960'])
        self.assertIn('<Socket nodeId="7960" itemId="0"/>', jewel_xml)

    def test_filled_socket_not_duplicated(self):
        equip = {'items': {}}
        items_dict = {
            '5': {'name': 'Test Jewel', 'rarity': 'rare',
                  'base': 'Metadata/Items/Jewels/JewelInt',
                  'implicits': [], 'explicits': []},
        }
        pob = self._FakePob()
        _, _, jewel_xml, _ = _itemset_xml_maxroll(
            equip, items_dict, pob, set_id=1, start_item_id=1,
            jewels_dict={'7960': 5}, tree_nodes=['7960'])
        # Should appear once with a real item ID, not with itemId="0"
        self.assertNotIn('itemId="0"', jewel_xml)
        self.assertIn('nodeId="7960"', jewel_xml)


if __name__ == '__main__':
    unittest.main()
