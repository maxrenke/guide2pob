import base64
import re
import unittest
import zlib

from moba2pob.convert import (
    convert, convert_merged, encode, _item_text, gem_name, _tree_nodes)
from tests.fixtures import sample_variant


class TestEncode(unittest.TestCase):

    def test_encode_round_trip(self):
        xml = '<PathOfBuilding2><Build/></PathOfBuilding2>'
        code = encode(xml)
        # Standard base64 - no URL-safe characters in normal output.
        self.assertRegex(code, r'^[A-Za-z0-9+/=]+$')
        decoded = zlib.decompress(base64.b64decode(code)).decode('utf-8')
        self.assertEqual(decoded, xml)


class TestConvertSingle(unittest.TestCase):

    def setUp(self):
        self.variant = sample_variant()
        self.meta = convert(
            self.variant, ascendancy_override='Lich', level=85,
            title='Endgame')

    def test_returns_round_trippable_code(self):
        xml = zlib.decompress(
            base64.b64decode(self.meta['code'])).decode('utf-8')
        self.assertEqual(xml, self.meta['xml'])

    def test_root_element_is_pob2(self):
        self.assertIn('<PathOfBuilding2>', self.meta['xml'])
        self.assertNotIn('<PathOfBuilding>', self.meta['xml'])

    def test_target_version_marks_poe2(self):
        self.assertIn('targetVersion="0_1"', self.meta['xml'])

    def test_build_has_player_stat_child(self):
        """pobb.in's parser requires a child inside <Build>."""
        m = re.search(r'<Build [^>]+>(.*?)</Build>', self.meta['xml'], re.S)
        self.assertIsNotNone(m)
        self.assertIn('<PlayerStat', m.group(1))

    def test_spec_has_full_class_identifiers(self):
        m = re.search(r'<Spec [^>]+>', self.meta['xml'])
        self.assertIsNotNone(m)
        attrs = m.group(0)
        for attr in ('classId="6"', 'ascendClassId="3"',
                      'classInternalId="1"', 'ascendancyInternalId="Witch3"',
                      'secondaryAscendClassId="0"',
                      'title="Endgame"'):
            self.assertIn(attr, attrs)

    def test_metadata(self):
        self.assertEqual(self.meta['class'], 'Witch')
        self.assertEqual(self.meta['ascendancy'], 'Lich')
        self.assertEqual(self.meta['node_count'], 3)  # 1 main + 2 ascendancy
        self.assertEqual(self.meta['skill_count'], 1)


class TestItemText(unittest.TestCase):

    def test_rare_item_format(self):
        slot = {
            'commonItem': {
                'isUnique': False, 'name': 'Altar Robe',
                'explicitDescriptions': [{'description': '+100 to Life'}],
            },
        }
        text = _item_text(slot, pob=None)
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: RARE')
        self.assertEqual(lines[1], 'Altar Robe')
        self.assertEqual(lines[2], 'Altar Robe')  # base type
        self.assertIn('--------', lines)
        self.assertIn('Item Level: 82', lines)
        self.assertIn('Implicits: 0', lines)
        self.assertIn('+100 to Life', lines)

    def test_unique_item_keeps_unique_rarity(self):
        slot = {
            'commonItem': {
                'isUnique': True, 'name': 'Atziri\'s Disdain',
                'explicitDescriptions': [],
            },
        }
        text = _item_text(slot, pob=None)
        self.assertTrue(text.startswith('Rarity: UNIQUE'))

    def test_weapon_set_slot_unwraps(self):
        slot = {'set1': {'commonItem': {
            'isUnique': False, 'name': 'Wand',
            'explicitDescriptions': []}}}
        text = _item_text(slot, pob=None)
        self.assertTrue(text.startswith('Rarity: RARE\nWand'))

    def test_empty_slot_returns_none(self):
        self.assertIsNone(_item_text(None, pob=None))
        self.assertIsNone(_item_text({}, pob=None))


class TestTreeNodes(unittest.TestCase):

    def test_filters_non_numeric(self):
        variant = {'passiveTree': {
            'mainTree': {'selectedSlugs': ['node-1', 'invalid', 'node-abc']},
            'ascendancyTree': {'selectedSlugs': ['node-2']},
        }}
        self.assertEqual(_tree_nodes(variant), ['1', '2'])


class TestGemNameFallback(unittest.TestCase):

    def test_prettify_without_pob_data(self):
        # No PoBData -> falls back to slug prettification.
        self.assertEqual(gem_name('contagionplayer', pob=None), 'Contagion')
        self.assertEqual(gem_name('darkeffigyplayer', pob=None), 'Darkeffigy')

    def test_strips_support_prefix(self):
        self.assertEqual(
            gem_name('supportunleashplayer', pob=None), 'Unleash')


class TestConvertMerged(unittest.TestCase):

    def test_two_variants_become_two_specs(self):
        v1 = sample_variant()
        v2 = sample_variant()
        v2['passiveTree']['mainTree']['selectedSlugs'] = [
            'node-1001', 'node-1002', 'node-1003']
        meta = convert_merged(
            [v1, v2], ascendancy_override='Lich',
            titles=['Leveling', 'Endgame'])
        specs = re.findall(r'<Spec [^>]+>', meta['xml'])
        skillsets = re.findall(r'<SkillSet [^>]+>', meta['xml'])
        itemsets = re.findall(r'<ItemSet [^>]+>', meta['xml'])
        self.assertEqual(len(specs), 2)
        self.assertEqual(len(skillsets), 2)
        self.assertEqual(len(itemsets), 2)

    def test_progression_order_sorts_by_node_count(self):
        v_small = sample_variant()
        v_small['passiveTree']['mainTree']['selectedSlugs'] = ['node-1']
        v_big = sample_variant()
        v_big['passiveTree']['mainTree']['selectedSlugs'] = [
            f'node-{i}' for i in range(50)]
        meta = convert_merged(
            [v_big, v_small], ascendancy_override='Lich',
            titles=['Endgame', 'Leveling'], progression_order=True)
        titles = re.findall(r'<Spec title="([^"]+)"', meta['xml'])
        self.assertEqual(titles, ['Leveling', 'Endgame'])

    def test_no_reorder_preserves_input_order(self):
        v_small = sample_variant()
        v_small['passiveTree']['mainTree']['selectedSlugs'] = ['node-1']
        v_big = sample_variant()
        v_big['passiveTree']['mainTree']['selectedSlugs'] = [
            f'node-{i}' for i in range(50)]
        meta = convert_merged(
            [v_big, v_small], ascendancy_override='Lich',
            titles=['Endgame', 'Leveling'], progression_order=False)
        titles = re.findall(r'<Spec title="([^"]+)"', meta['xml'])
        self.assertEqual(titles, ['Endgame', 'Leveling'])

    def test_empty_variants_raises(self):
        with self.assertRaises(ValueError):
            convert_merged([], ascendancy_override='Lich')


if __name__ == '__main__':
    unittest.main()
