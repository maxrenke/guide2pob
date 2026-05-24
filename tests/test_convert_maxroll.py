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


class TestItemText(unittest.TestCase):

    def test_rare_item_with_mods(self):
        item = {
            'name': 'Plague Wand',
            'rarity': 'rare',
            'base': 'Metadata/Items/Weapons/OneHandWeapons/Wands/FourWandInt',
            'implicits': [{'text': '20% increased Spell Damage'}],
            'explicits': [{'text': '+50 to Maximum Mana'}],
        }
        text = _item_text(item, pob=None)
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: RARE')
        self.assertIn('Implicits: 1', lines)
        self.assertIn('20% increased Spell Damage', lines)
        self.assertIn('+50 to Maximum Mana', lines)

    def test_unique_item_uses_fallback_base(self):
        item = {
            'name': 'Tabula Rasa',
            'rarity': 'unique',
            'base': 'Metadata/Items/Armours/BodyArmours/FourBodyInt',
        }
        text = _item_text(item, pob=None)
        self.assertIn('Rarity: UNIQUE', text)
        # Should use fallback dict for Tabula Rasa
        self.assertIn('Simple Robe', text)

    def test_magic_item_rarity(self):
        item = {
            'name': 'Rare Amulet',
            'rarity': 'magic',
            'base': 'Metadata/Items/Amulets/FourAmuletInt',
            'implicits': [],
            'explicits': [{'text': '+20 to all Attributes'}],
        }
        text = _item_text(item, pob=None)
        self.assertIn('Rarity: MAGIC', text)
        self.assertIn('+20 to all Attributes', text)

    def test_mod_text_as_plain_string(self):
        item = {
            'name': 'Test Helm',
            'rarity': 'rare',
            'base': 'Metadata/Items/Armours/Helmets/FourHelmetStr',
            'implicits': [],
            'explicits': ['plain string mod'],
        }
        text = _item_text(item, pob=None)
        self.assertIn('plain string mod', text)

    def test_no_mods_gives_implicits_zero(self):
        item = {'name': 'Empty Helm', 'rarity': 'rare',
                'base': 'Metadata/Items/Armours/Helmets/FourHelmetInt'}
        text = _item_text(item, pob=None)
        self.assertIn('Implicits: 0', text)

    def test_none_returns_none(self):
        self.assertIsNone(_item_text(None, pob=None))


class TestConvertSingle(unittest.TestCase):

    def setUp(self):
        self.planner = sample_maxroll_planner()
        self.meta = convert(self.planner, _PROFILE, variant_idx=1, level=90)

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
        self.assertIn('+50 to Maximum Mana', self.meta['xml'])

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
