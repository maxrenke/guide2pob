"""Tests for convert_poe1.py - the PoE1 Mobalytics -> PoB conversion path."""
import base64
import re
import unittest
import zlib

from moba2pob.convert_poe1 import (
    decode_pobcode, _class_info_from_xml, _item_text, _jewel_text,
    _mastery_string, _skill_groups, _tree_nodes, encode, convert,
    convert_merged)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xml(class_name='Witch', ascend_name='Occultist', extra=''):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PathOfBuilding>'
        '<Build className="%s" ascendClassName="%s" level="90"/>'
        '%s'
        '</PathOfBuilding>' % (class_name, ascend_name, extra)
    )


def _make_pobcode(xml):
    return base64.b64encode(zlib.compress(xml.encode(), 9)).decode()


def _make_doc(class_name='Witch', ascend_name='Occultist', extra='',
              variants=None):
    """Build a minimal PoE1 doc dict with an embedded pobCode."""
    xml = _make_xml(class_name, ascend_name, extra)
    doc = {'pobCode': _make_pobcode(xml)}
    if variants is not None:
        doc['buildVariants'] = {'values': variants}
    else:
        doc['buildVariants'] = {'values': [_make_variant()]}
    return doc


def _make_variant(node_ids=('11111',), gem_names=('Fireball',)):
    return {
        'passiveTree': {
            'mainTree': {'selectedSlugs': ['node-%s' % n for n in node_ids]},
            'ascendancyTree': {'selectedSlugs': []},
            'alternateAscendancyTree': {'selectedSlugs': []},
            'masteries': [],
            'jewels': [],
        },
        'skills': {'gemGroups': [
            {
                'slotSlug': 'mainHand',
                'label': 'Main Skill',
                'gems': [
                    {'skillGemObject': {'data': {'name': nm}}}
                    for nm in gem_names
                ],
            }
        ]},
        'genericBuilder': {'slots': []},
    }


# ---------------------------------------------------------------------------
# decode_pobcode / _class_info_from_xml
# ---------------------------------------------------------------------------

class TestDecodePobbCode(unittest.TestCase):

    def test_round_trip(self):
        xml = _make_xml()
        code = _make_pobcode(xml)
        doc = {'pobCode': code}
        decoded = decode_pobcode(doc)
        self.assertEqual(decoded, xml)

    def test_missing_code_raises(self):
        with self.assertRaises(ValueError):
            decode_pobcode({})

    def test_class_info_extraction(self):
        cls, asc = _class_info_from_xml(_make_xml('Shadow', 'Assassin'))
        self.assertEqual(cls, 'Shadow')
        self.assertEqual(asc, 'Assassin')

    def test_class_info_missing_returns_none(self):
        cls, asc = _class_info_from_xml('<PathOfBuilding/>')
        self.assertIsNone(cls)
        self.assertIsNone(asc)


# ---------------------------------------------------------------------------
# _item_text (PoE1 format)
# ---------------------------------------------------------------------------

class TestPoe1ItemText(unittest.TestCase):

    def _slot(self, rarity='RARE', title='Great Helm', name='New Item',
              sub_title='', implicits=None, explicits=None):
        return {
            'gameSlotSlug': 'helmet',
            'gameEntity': {
                'title': title,
                'data': {
                    'rarity': rarity,
                    'name': name,
                    'subTitle': sub_title,
                    'implicitMods': implicits or [],
                    'explicitMods': explicits or [{'text': '+100 to Life'}],
                },
            },
        }

    def test_rare_format(self):
        text = _item_text(self._slot())
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: RARE')
        self.assertIn('Item Level: 82', lines)
        self.assertIn('Implicits: 0', lines)
        self.assertIn('+100 to Life', lines)

    def test_unique_format(self):
        text = _item_text(self._slot(
            rarity='UNIQUE', title='Headhunter',
            sub_title='Leather Belt', name='Headhunter'))
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: UNIQUE')
        self.assertEqual(lines[1], 'Headhunter')
        self.assertEqual(lines[2], 'Leather Belt')

    def test_implicits_counted(self):
        text = _item_text(self._slot(
            implicits=[{'text': '+50 to Mana'}],
            explicits=[{'text': '+100 to Life'}]))
        self.assertIn('Implicits: 1', text)
        self.assertIn('+50 to Mana', text)
        self.assertIn('--------', text)

    def test_no_game_entity_returns_none(self):
        self.assertIsNone(_item_text({'gameSlotSlug': 'helmet'}))


# ---------------------------------------------------------------------------
# _jewel_text (PoE1 format)
# ---------------------------------------------------------------------------

class TestPoe1JewelText(unittest.TestCase):

    def _jewel_entry(self, rarity='RARE', name='New Item',
                     sub_title='Viridian Jewel', explicits=None):
        return {
            'nodeSlug': 'node-61834',
            'jewel': {
                'data': {
                    'rarity': rarity,
                    'name': name,
                    'subTitle': sub_title,
                    'implicitMods': [],
                    'explicitMods': explicits or [{'text': '+5% to Area of Effect'}],
                },
                'entityV2': {'name': sub_title},
            },
        }

    def test_rare_jewel(self):
        text = _jewel_text(self._jewel_entry())
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: RARE')
        self.assertEqual(lines[2], 'Viridian Jewel')

    def test_unique_jewel(self):
        text = _jewel_text(self._jewel_entry(
            rarity='UNIQUE', name='The Covenant',
            sub_title='Cobalt Jewel'))
        lines = text.split('\n')
        self.assertEqual(lines[0], 'Rarity: UNIQUE')
        self.assertEqual(lines[1], 'The Covenant')
        self.assertEqual(lines[2], 'Cobalt Jewel')


# ---------------------------------------------------------------------------
# _mastery_string
# ---------------------------------------------------------------------------

class TestMasteryString(unittest.TestCase):

    def test_encodes_masteries(self):
        variant = {'passiveTree': {'masteries': [
            {'passiveSkillNode': {'slug': 'node-100'},
             'mastery': {'slug': '42'}},
            {'passiveSkillNode': {'slug': 'node-200'},
             'mastery': {'slug': '99'}},
        ]}}
        result = _mastery_string(variant)
        self.assertIn('{100,42}', result)
        self.assertIn('{200,99}', result)

    def test_no_masteries_returns_empty(self):
        self.assertEqual(_mastery_string({'passiveTree': {}}), '')
        self.assertEqual(_mastery_string({}), '')

    def test_non_numeric_node_skipped(self):
        variant = {'passiveTree': {'masteries': [
            {'passiveSkillNode': {'slug': 'passive-abc'},
             'mastery': {'slug': '5'}},
        ]}}
        self.assertEqual(_mastery_string(variant), '')


# ---------------------------------------------------------------------------
# _skill_groups
# ---------------------------------------------------------------------------

class TestPoe1SkillGroups(unittest.TestCase):

    def test_extracts_gem_names(self):
        variant = _make_variant(gem_names=('Fireball', 'Greater Multiple Projectiles'))
        groups = _skill_groups(variant)
        self.assertEqual(len(groups), 1)
        self.assertIn('Fireball', groups[0]['gems'])
        self.assertIn('Greater Multiple Projectiles', groups[0]['gems'])

    def test_empty_gems_skipped(self):
        variant = {'skills': {'gemGroups': [
            {'slotSlug': 'mainHand', 'label': 'Skill',
             'gems': [{'skillGemObject': {'data': {'name': ''}}}]}
        ]}}
        self.assertEqual(_skill_groups(variant), [])


# ---------------------------------------------------------------------------
# convert (pobCode path)
# ---------------------------------------------------------------------------

class TestConvertPoe1PobCode(unittest.TestCase):

    def setUp(self):
        self.doc = _make_doc()
        self.meta = convert(self.doc)  # variant_idx=None -> pobCode path

    def test_source_is_pobcode(self):
        self.assertEqual(self.meta['source'], 'pobCode')

    def test_class_extracted_correctly(self):
        self.assertEqual(self.meta['class'], 'Witch')
        self.assertEqual(self.meta['ascendancy'], 'Occultist')

    def test_code_round_trips(self):
        xml = zlib.decompress(base64.b64decode(self.meta['code'])).decode()
        self.assertEqual(xml, self.meta['xml'])

    def test_pob1_root_element(self):
        self.assertIn('<PathOfBuilding>', self.meta['xml'])
        self.assertNotIn('<PathOfBuilding2>', self.meta['xml'])

    def test_notes_injected(self):
        meta = convert(self.doc, notes='My notes here')
        self.assertIn('<Notes>', meta['xml'])
        self.assertIn('My notes here', meta['xml'])

    def test_notes_no_duplicate_when_existing_notes_present(self):
        # pobCode XML that already has a <Notes> block.
        xml_with_notes = _make_xml(extra='<Notes>Original notes</Notes>')
        doc = {'pobCode': _make_pobcode(xml_with_notes),
               'buildVariants': {'values': [_make_variant()]}}
        meta = convert(doc, notes='New notes')
        # Only one <Notes> element should exist.
        self.assertEqual(meta['xml'].count('<Notes>'), 1)
        self.assertIn('New notes', meta['xml'])
        self.assertNotIn('Original notes', meta['xml'])


# ---------------------------------------------------------------------------
# convert (structured path)
# ---------------------------------------------------------------------------

class TestConvertPoe1Structured(unittest.TestCase):

    def setUp(self):
        self.doc = _make_doc()
        self.meta = convert(self.doc, variant_idx=0, ascendancy_override='Occultist')

    def test_source_is_structured(self):
        self.assertEqual(self.meta['source'], 'structured')

    def test_class_from_override(self):
        self.assertEqual(self.meta['class'], 'Witch')
        self.assertEqual(self.meta['ascendancy'], 'Occultist')

    def test_pob1_root_element(self):
        self.assertIn('<PathOfBuilding>', self.meta['xml'])

    def test_target_version_3_0(self):
        self.assertIn('targetVersion="3_0"', self.meta['xml'])

    def test_gem_in_output(self):
        self.assertIn('Fireball', self.meta['xml'])

    def test_node_count(self):
        self.assertEqual(self.meta['node_count'], 1)


# ---------------------------------------------------------------------------
# convert_merged
# ---------------------------------------------------------------------------

class TestConvertMergedPoe1(unittest.TestCase):

    def _two_variant_doc(self):
        v_small = _make_variant(node_ids=('1',))
        v_big = _make_variant(node_ids=tuple(str(i) for i in range(20)))
        return _make_doc(variants=[v_big, v_small])

    def test_two_specs_produced(self):
        doc = self._two_variant_doc()
        meta = convert_merged(doc, ascendancy_override='Occultist',
                               titles=['Endgame', 'Leveling'])
        specs = re.findall(r'<Spec [^>]+>', meta['xml'])
        self.assertEqual(len(specs), 2)

    def test_progression_order_sorts_ascending(self):
        doc = self._two_variant_doc()
        meta = convert_merged(doc, ascendancy_override='Occultist',
                               titles=['Endgame', 'Leveling'],
                               progression_order=True)
        titles = re.findall(r'<Spec title="([^"]+)"', meta['xml'])
        self.assertEqual(titles, ['Leveling', 'Endgame'])

    def test_no_reorder_preserves_order(self):
        doc = self._two_variant_doc()
        meta = convert_merged(doc, ascendancy_override='Occultist',
                               titles=['Endgame', 'Leveling'],
                               progression_order=False)
        titles = re.findall(r'<Spec title="([^"]+)"', meta['xml'])
        self.assertEqual(titles, ['Endgame', 'Leveling'])

    def test_empty_doc_raises(self):
        doc = _make_doc(variants=[])
        with self.assertRaises(ValueError):
            convert_merged(doc, ascendancy_override='Occultist')

    def test_variant_count_in_meta(self):
        doc = self._two_variant_doc()
        meta = convert_merged(doc, ascendancy_override='Occultist')
        self.assertEqual(meta['variant_count'], 2)


if __name__ == '__main__':
    unittest.main()
