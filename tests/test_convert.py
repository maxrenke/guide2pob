import base64
import re
import unittest
import zlib

from guide2pob.convert import (
    convert, convert_merged, encode, _item_text, gem_name, _tree_nodes,
    _common_item, _attribute_overrides, _weapon_set_tree_nodes,
    _humanize_rune, _jewel_text, _jewel_base_name, _enumerate_slot,
    _priority_notes)
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

    def test_notes_element_present(self):
        meta = convert(self.variant, ascendancy_override='Lich',
                       notes='My build notes')
        self.assertIn('<Notes>', meta['xml'])
        self.assertIn('My build notes', meta['xml'])

    def test_priority_list_appended_to_notes(self):
        # sample_variant has a non-empty priorityList, so even with no
        # explicit notes the <Notes> element should mention priorities.
        meta = convert(self.variant, ascendancy_override='Lich')
        self.assertIn('Ascendancy Priority', meta['xml'])
        self.assertIn('Soulless Form', meta['xml'])

    def test_jewel_socket_in_spec(self):
        # sample_variant has one jewel at node-7960.
        meta = convert(self.variant, ascendancy_override='Lich')
        self.assertIn('<Socket nodeId="7960"', meta['xml'])
        self.assertIn('<Sockets>', meta['xml'])

    def test_jewel_item_in_items_section(self):
        # PoE2 jewel base names have no " Jewel" suffix.
        meta = convert(self.variant, ascendancy_override='Lich')
        self.assertIn('Sapphire', meta['xml'])


class TestItemText(unittest.TestCase):

    def test_rare_item_format(self):
        item = {
            'isUnique': False, 'name': 'Altar Robe',
            'explicitDescriptions': [{'description': '+100 to Life'}],
        }
        text = _item_text(item)
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: RARE')
        self.assertEqual(lines[1], 'Altar Robe')
        self.assertEqual(lines[2], 'Altar Robe')  # base type
        self.assertIn('--------', lines)
        self.assertIn('Item Level: 82', lines)
        self.assertIn('Implicits: 0', lines)
        self.assertIn('+100 to Life', lines)

    def test_unique_item_keeps_unique_rarity(self):
        item = {'isUnique': True, 'name': 'Atziri\'s Disdain',
                'explicitDescriptions': []}
        text = _item_text(item)
        self.assertTrue(text.startswith('Rarity: UNIQUE'))

    def test_runes_become_sockets(self):
        item = {'isUnique': False, 'name': 'Altar Robe',
                'explicitDescriptions': []}
        runes = [{'slug': 'soulcore-enhance'}, {'slug': 'soulcore-defense'}]
        text = _item_text(item, runes=runes)
        self.assertIn('Sockets: S S', text)
        self.assertIn('Rune: Soulcore Enhance', text)
        self.assertIn('Rune: Soulcore Defense', text)

    def test_anointment_becomes_enchant_line(self):
        item = {'isUnique': False, 'name': 'Lunar Amulet',
                'explicitDescriptions': []}
        text = _item_text(
            item,
            anointment={'description': 'Allocates Forces of Nature'})
        self.assertIn('Allocates Forces of Nature (enchant)', text)

    def test_empty_returns_none(self):
        self.assertIsNone(_item_text(None))
        self.assertIsNone(_item_text({}))


class TestSlotUnwrap(unittest.TestCase):

    def test_common_item_path(self):
        self.assertEqual(_common_item({'commonItem': {'name': 'x'}}),
                          {'name': 'x'})

    def test_weapon_set(self):
        slot = {'set1': {'commonItem': {'name': 'wand'}}}
        self.assertEqual(_common_item(slot), {'name': 'wand'})


class TestPassiveTreeExtras(unittest.TestCase):

    def test_attribute_overrides_group_by_attribute(self):
        variant = {'passiveTree': {'attributeNodes': [
            {'attribute': 'str', 'nodeSlug': 'node-100'},
            {'attribute': 'dex', 'nodeSlug': 'node-200'},
            {'attribute': 'str', 'nodeSlug': 'node-300'},
            {'attribute': 'int', 'nodeSlug': 'node-400'},
        ]}}
        out = _attribute_overrides(variant)
        self.assertEqual(out['str'], ['100', '300'])
        self.assertEqual(out['dex'], ['200'])
        self.assertEqual(out['int'], ['400'])

    def test_weapon_set_tree_nodes(self):
        variant = {'passiveTree': {
            'set1Tree': {'selectedSlugs': ['node-1', 'node-2']},
            'set2Tree': {'selectedSlugs': ['node-3']},
        }}
        out = _weapon_set_tree_nodes(variant)
        self.assertEqual(out, {1: ['1', '2'], 2: ['3']})

    def test_humanize_rune(self):
        self.assertEqual(
            _humanize_rune('soulcore-runeenhancegreater'),
            'Soulcore Runeenhancegreater')


class TestEnumerateSlot(unittest.TestCase):

    def test_single_item_slot(self):
        slot = {'commonItem': {'name': 'helmet', 'isUnique': False,
                               'explicitDescriptions': []}}
        results = list(_enumerate_slot(slot))
        self.assertEqual(len(results), 1)
        item, runes, anoint, ws_idx = results[0]
        self.assertEqual(item['name'], 'helmet')
        self.assertEqual(ws_idx, 0)

    def test_weapon_set_yields_both(self):
        slot = {
            'set1': {'commonItem': {'name': 'Wand', 'isUnique': False,
                                    'explicitDescriptions': []}},
            'set2': {'commonItem': {'name': 'Staff', 'isUnique': False,
                                    'explicitDescriptions': []}},
        }
        results = list(_enumerate_slot(slot))
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0]['name'], 'Wand')
        self.assertEqual(results[0][3], 0)
        self.assertEqual(results[1][0]['name'], 'Staff')
        self.assertEqual(results[1][3], 1)

    def test_weapon_set_one_empty(self):
        slot = {
            'set1': {'commonItem': {'name': 'Wand', 'isUnique': False,
                                    'explicitDescriptions': []}},
            'set2': None,
        }
        results = list(_enumerate_slot(slot))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0]['name'], 'Wand')

    def test_empty_slot_yields_nothing(self):
        self.assertEqual(list(_enumerate_slot(None)), [])
        self.assertEqual(list(_enumerate_slot({})), [])


class TestJewelText(unittest.TestCase):

    def test_known_slug_maps_to_base_name(self):
        # PoE2 uses short names without the " Jewel" suffix.
        self.assertEqual(_jewel_base_name('jewel-jewelint'), 'Sapphire')
        self.assertEqual(_jewel_base_name('jewel-jewelstr'), 'Ruby')
        self.assertEqual(_jewel_base_name('jewel-jeweldex'), 'Emerald')

    def test_unknown_slug_falls_back_gracefully(self):
        # Any unknown slug returns the Diamond fallback (safest generic base).
        result = _jewel_base_name('jewel-jewelstrdexint')
        self.assertEqual(result, 'Diamond')

    def test_rare_jewel_text_format(self):
        jewel = {'isUnique': False, 'jewelSlug': 'jewel-jewelint',
                 'nodeSlug': 'node-7960'}
        text = _jewel_text(jewel, pob=None)
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: RARE')
        self.assertEqual(lines[1], 'Sapphire')
        self.assertEqual(lines[2], 'Sapphire')
        self.assertIn('Item Level: 82', lines)
        self.assertIn('Implicits: 0', lines)

    def test_unique_jewel_uses_unique_rarity(self):
        jewel = {'isUnique': True, 'jewelSlug': 'jewel-voices',
                 'jewelName': 'The Voices', 'nodeSlug': 'node-1000'}
        text = _jewel_text(jewel, pob=None)
        self.assertTrue(text.startswith('Rarity: UNIQUE'))
        self.assertIn('The Voices', text)


class TestPriorityNotes(unittest.TestCase):

    def test_empty_priority_list_returns_empty_string(self):
        variant = {'passiveTree': {'ascendancyTree': {'priorityList': []}}}
        self.assertEqual(_priority_notes(variant), '')

    def test_missing_priority_list_returns_empty_string(self):
        self.assertEqual(_priority_notes({}), '')

    def test_formats_ascendancy_priority_list(self):
        variant = {'passiveTree': {'ascendancyTree': {'priorityList': [
            {'slug': 'node-1', 'name': 'Soulless Form'},
            {'slug': 'node-2', 'name': 'Eternal Life'},
        ]}}}
        result = _priority_notes(variant)
        self.assertIn('Ascendancy Priority:', result)
        self.assertIn('1. Soulless Form', result)
        self.assertIn('2. Eternal Life', result)

    def test_formats_equipment_priority_list(self):
        variant = {'equipment': {'priorityList': [
            {'name': 'Atziri\'s Disdain', 'type': 'helmet'},
            {'name': 'Snakepit', 'type': 'rightRing'},
        ]}}
        result = _priority_notes(variant)
        self.assertIn('Equipment Priority:', result)
        self.assertIn("1. Atziri's Disdain (helmet)", result)
        self.assertIn('2. Snakepit (rightRing)', result)

    def test_formats_gem_priority_list_with_display_names(self):
        variant = {
            'skillGems': {
                'gems': [
                    {'activeSkill': {'gemSlug': 'contagionplayer',
                                     'name': 'Contagion'},
                     'subSkills': []},
                ],
                'priorityGems': [
                    {'name': 'Unleash', 'gemSlug': 'supportunleashplayer',
                     'parentActiveSkillGemSlug': 'contagionplayer'},
                    {'name': 'Chain II', 'gemSlug': 'supportchainplayertwo',
                     'parentActiveSkillGemSlug': 'contagionplayer'},
                ],
            },
        }
        result = _priority_notes(variant)
        self.assertIn('Gem Priorities:', result)
        # Parent slug should resolve to display name "Contagion" not the raw slug.
        self.assertIn('Contagion:', result)
        self.assertIn('Unleash', result)
        self.assertIn('Chain II', result)


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


class TestEmptyJewelSocket(unittest.TestCase):
    """Allocated jewel-socket nodes with no jewel must emit itemId="0" sockets.

    Without this PoB2 crashes in PassiveSpec.lua:1079 when it tries to look up
    the jewel for a containJewelSocket node that has no <Socket> entry.
    """

    class _FakePob:
        """Minimal PoBData stand-in that reports node-9999 as a jewel socket."""
        jewel_socket_nodes = {'9999'}
        tree_version = '0_4'
        gems = {}
        unique_bases = {}

    def test_empty_allocated_socket_gets_item_id_zero(self):
        variant = sample_variant()
        # Allocate a jewel-socket node but give it no jewel.
        variant['passiveTree']['mainTree']['selectedSlugs'].append('node-9999')
        pob = self._FakePob()
        meta = convert(variant, pob=pob, ascendancy_override='Lich')
        self.assertIn('<Socket nodeId="9999" itemId="0"/>', meta['xml'])

    def test_filled_socket_does_not_get_extra_empty_entry(self):
        variant = sample_variant()
        # node-7960 already has a jewel in sample_variant.
        pob = self._FakePob()
        pob.jewel_socket_nodes = {'7960'}
        meta = convert(variant, pob=pob, ascendancy_override='Lich')
        # Should appear exactly once (the filled one), NOT with itemId="0".
        self.assertNotIn('<Socket nodeId="7960" itemId="0"/>', meta['xml'])
        # The filled socket has a non-zero item id.
        import re
        sockets = re.findall(r'<Socket nodeId="7960" itemId="(\d+)"', meta['xml'])
        self.assertEqual(len(sockets), 1)
        self.assertNotEqual(sockets[0], '0')


class TestWeaponSetSwap(unittest.TestCase):

    def test_set2_weapon_becomes_swap_slot(self):
        variant = sample_variant()
        # Add a weapon set 2 item to mainHand.
        variant['equipment']['mainHand']['set2'] = {
            'commonItem': {
                'name': 'Plague Staff',
                'isUnique': False,
                'itemClassSlug': 'staff',
                'explicitDescriptions': [{'description': '+50 to Chaos Damage'}],
            }
        }
        meta = convert(variant, ascendancy_override='Lich')
        self.assertIn('Weapon 1 Swap', meta['xml'])
        self.assertIn('Plague Staff', meta['xml'])
        self.assertIn('useSecondWeaponSet="true"', meta['xml'])

    def test_no_set2_weapon_no_swap_slot(self):
        variant = sample_variant()
        meta = convert(variant, ascendancy_override='Lich')
        self.assertNotIn('Weapon 1 Swap', meta['xml'])
        self.assertIn('useSecondWeaponSet="false"', meta['xml'])


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
