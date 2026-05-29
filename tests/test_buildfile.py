"""Tests for .build file generation (buildfile.py) and the cli hook."""
import json
import os
import tempfile
import types
import unittest

from guide2pob import buildfile
from guide2pob.buildfile import (
    build_node_id_map, parse_pob_xml, build_dotbuild, _ascendancy_internal_id,
    _item_name_and_unique, _item_first_line, safe_filename, write_buildfile,
    find_buildplanner_dir, _gem_name_to_id, item_additional_text,
)


class TestItemAdditionalText(unittest.TestCase):
    def test_rare_header_is_base_with_numbered_mods(self):
        text = ('Rarity: RARE\nGloom Horn\nWithered Wand\n--------\n'
                'Item Level: 82\n--------\nImplicits: 0\n'
                '44% increased Spell Damage\n+1 to Level of all Chaos Spell Skills')
        out = item_additional_text(text)
        self.assertEqual(
            out,
            'Withered Wand\n1. 44% increased Spell Damage\n'
            '2. +1 to Level of all Chaos Spell Skills')

    def test_skips_implicit_lines(self):
        # PoB lists implicits then explicits contiguously (no separator between).
        text = ('Rarity: RARE\nx\nSapphire Ring\n--------\nImplicits: 1\n'
                '+20% to Cold Resistance\n+50 to maximum Life')
        out = item_additional_text(text)
        self.assertEqual(out, 'Sapphire Ring\n1. +50 to maximum Life')

    def test_stops_at_trailer(self):
        text = ('Rarity: RARE\nx\nWand\n--------\nImplicits: 0\n'
                '10% increased Cast Speed\n--------\nCorrupted')
        self.assertEqual(item_additional_text(text), 'Wand\n1. 10% increased Cast Speed')

    def test_unique_header_is_name(self):
        text = "Rarity: UNIQUE\nAtziri's Disdain\nHubris Circlet"
        self.assertEqual(item_additional_text(text), "Atziri's Disdain")

    def test_non_item_returns_none(self):
        self.assertIsNone(item_additional_text('just text'))
        self.assertIsNone(item_additional_text(''))


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding2>
  <Build className="Witch" ascendClassName="Lich" level="92">
    <PlayerStat stat="Life" value="1600"/>
  </Build>
  <Tree activeSpec="1">
    <Spec nodes="100,200"/>
    <Spec nodes="100,200,300,400,500"/>
  </Tree>
  <Skills activeSkillSet="1">
    <SkillSet>
      <Skill label="Main">
        <Gem nameSpec="Essence Drain" enabled="true"/>
        <Gem nameSpec="Controlled Destruction" enabled="true"/>
        <Gem nameSpec="Disabled Gem" enabled="false"/>
      </Skill>
    </SkillSet>
  </Skills>
  <Items activeItemSet="1">
    <Item id="1">Rarity: RARE
Withered Wand
Withered Wand
--------
+1 to Level of all Chaos Spell Skills</Item>
    <Item id="2">Rarity: UNIQUE
Atziri's Disdain
Hubris Circlet</Item>
    <ItemSet>
      <Slot name="Weapon 1" itemId="1"/>
      <Slot name="Helmet" itemId="2"/>
    </ItemSet>
  </Items>
  <Notes>My Build
https://mobalytics.gg/poe-2/builds/x</Notes>
</PathOfBuilding2>"""


def _fake_pob_with_gems():
    """A stand-in PoBData exposing .path with a Data/Gems.lua the parser reads."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, 'Data'), exist_ok=True)
    gems = (
        'return {\n'
        '["Metadata/Items/Gems/EssenceDrain"] = {\n'
        '\tname = "Essence Drain",\n'
        '\t},\n'
        '["Metadata/Items/Gems/SupportControlledDestruction"] = {\n'
        '\tname = "Controlled Destruction",\n'
        '\t},\n'
        '}\n'
    )
    with open(os.path.join(d, 'Data', 'Gems.lua'), 'w', encoding='utf-8') as f:
        f.write(gems)
    return types.SimpleNamespace(path=d)


class TestNodeIdMap(unittest.TestCase):
    def test_maps_numeric_to_string_id(self):
        export = {'nodes': {
            'a': {'skill': 100, 'id': 'strength1'},
            'b': {'skill': 200, 'id': 'dexterity1'},
            'c': {'skill': None, 'id': 'ignored'},   # no skill -> skipped
            'd': {'id': 'no_skill'},                  # missing skill -> skipped
        }}
        m = build_node_id_map(export)
        self.assertEqual(m, {'100': 'strength1', '200': 'dexterity1'})

    def test_empty_export(self):
        self.assertEqual(build_node_id_map({}), {})


class TestParsePobXml(unittest.TestCase):
    def test_largest_prefers_biggest_spec(self):
        p = parse_pob_xml(SAMPLE_XML, prefer='largest')
        self.assertEqual(p['node_ids'], ['100', '200', '300', '400', '500'])
        self.assertEqual(p['class_name'], 'Witch')
        self.assertEqual(p['ascend_name'], 'Lich')
        self.assertEqual(p['level'], 92)

    def test_active_uses_active_spec(self):
        p = parse_pob_xml(SAMPLE_XML, prefer='active')
        self.assertEqual(p['node_ids'], ['100', '200'])  # activeSpec=1 -> first

    def test_skill_groups_skip_disabled_gems(self):
        p = parse_pob_xml(SAMPLE_XML, prefer='largest')
        self.assertEqual(len(p['skill_groups']), 1)
        self.assertEqual(p['skill_groups'][0]['gems'],
                         ['Essence Drain', 'Controlled Destruction'])

    def test_slot_and_item_maps(self):
        p = parse_pob_xml(SAMPLE_XML, prefer='largest')
        self.assertEqual(p['slot_map']['Weapon 1'], '1')
        self.assertEqual(p['slot_map']['Helmet'], '2')
        self.assertIn('Withered Wand', p['items_by_id']['1'])
        self.assertIn('mobalytics.gg', p['notes'])


class TestItemHelpers(unittest.TestCase):
    def test_unique_detected(self):
        name, uniq = _item_name_and_unique('Rarity: UNIQUE\nAtziri\'s Disdain\nHubris Circlet')
        self.assertEqual(name, "Atziri's Disdain")
        self.assertTrue(uniq)

    def test_rare_not_unique(self):
        name, uniq = _item_name_and_unique('Rarity: RARE\nFoo Bar\nWand')
        self.assertEqual(name, 'Foo Bar')
        self.assertFalse(uniq)

    def test_no_rarity_line(self):
        self.assertEqual(_item_name_and_unique('just text'), (None, False))

    def test_first_line(self):
        self.assertEqual(_item_first_line('Rarity: RARE\nx'), 'Rarity: RARE')
        self.assertIsNone(_item_first_line('no rarity here'))
        self.assertIsNone(_item_first_line(''))


class TestAscendancyId(unittest.TestCase):
    def test_known(self):
        self.assertTrue(_ascendancy_internal_id('Lich'))

    def test_case_insensitive(self):
        self.assertEqual(_ascendancy_internal_id('lich'),
                         _ascendancy_internal_id('Lich'))

    def test_unknown(self):
        self.assertIsNone(_ascendancy_internal_id('Not An Ascendancy'))


class TestBuildDotbuild(unittest.TestCase):
    def setUp(self):
        self.parsed = parse_pob_xml(SAMPLE_XML, prefer='largest')
        self.node_map = {'100': 'strength1', '200': 'dexterity1',
                         '300': 'intelligence1'}  # 400,500 intentionally unmapped

    def test_core_fields(self):
        doc = build_dotbuild(self.parsed, node_id_map=self.node_map,
                             name='My Build', source_url='https://x', author='me')
        self.assertEqual(doc['name'], 'My Build')
        self.assertEqual(doc['author'], 'me')
        self.assertIn('https://x', doc['description'])
        self.assertEqual(doc['ascendancy'], _ascendancy_internal_id('Lich'))

    def test_passives_are_id_objects(self):
        doc = build_dotbuild(self.parsed, node_id_map=self.node_map, name='b')
        self.assertEqual(doc['passives'],
                         [{'id': 'strength1'}, {'id': 'dexterity1'},
                          {'id': 'intelligence1'}])

    def test_skills_resolved_via_gem_map(self):
        pob = _fake_pob_with_gems()
        doc = build_dotbuild(self.parsed, pob=pob, node_id_map=self.node_map, name='b')
        self.assertEqual(len(doc['skills']), 1)
        sk = doc['skills'][0]
        self.assertEqual(sk['id'], 'Metadata/Items/Gems/EssenceDrain')
        self.assertEqual(sk['level_interval'], [1, 100])
        self.assertEqual(sk['support_skills'],
                         [{'id': 'Metadata/Items/Gems/SupportControlledDestruction',
                           'level_interval': [1, 100]}])

    def test_skills_omitted_without_pob(self):
        doc = build_dotbuild(self.parsed, pob=None, node_id_map=self.node_map, name='b')
        self.assertNotIn('skills', doc)

    def test_inventory_additional_text_and_ids(self):
        doc = build_dotbuild(self.parsed, node_id_map=self.node_map, name='b')
        inv = {e['inventory_id']: e for e in doc['inventory_slots']}
        # PoB 'Weapon 1' -> 'Weapon1', 'Helmet' -> 'Helm' (official id scheme)
        self.assertIn('Weapon1', inv)
        self.assertIn('Helm', inv)
        # unique helmet -> additional_text header is the unique name
        self.assertTrue(inv['Helm']['additional_text'].startswith("Atziri's Disdain"))
        # every entry carries the full official shape
        for e in inv.values():
            self.assertEqual(e['level_interval'], [1, 100])
            self.assertEqual((e['slot_x'], e['slot_y']), (0, 0))
            self.assertIn('additional_text', e)


class TestFsHelpers(unittest.TestCase):
    def test_safe_filename(self):
        self.assertEqual(safe_filename('a/b:c*?.build'), 'a_b_c__.build')
        self.assertEqual(safe_filename(''), 'build')
        self.assertEqual(safe_filename('  x  '), 'x')
        self.assertLessEqual(len(safe_filename('z' * 500)), 120)

    def test_find_buildplanner_dir_default(self):
        p = find_buildplanner_dir()
        self.assertIn('Path of Exile 2', p)
        self.assertTrue(p.endswith(os.path.join('Preferences', 'BuildPlanner')))

    def test_find_buildplanner_dir_explicit(self):
        self.assertEqual(find_buildplanner_dir('/x/y'), '/x/y')

    def test_write_buildfile_roundtrip(self):
        d = tempfile.mkdtemp()
        doc = {'name': 'b', 'passives': ['strength1']}
        path = write_buildfile(doc, os.path.join(d, 'sub'), 'b.build')
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding='utf-8') as f:
            self.assertEqual(json.load(f), doc)


MULTI_VARIANT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding2>
  <Build className="Witch" ascendClassName="Lich" level="92"/>
  <Tree>
    <Spec nodes="100"/>
    <Spec nodes="100,200,300"/>
  </Tree>
  <Skills>
    <SkillSet title="ACT 1">
      <Skill label="Main"><Gem nameSpec="Essence Drain" enabled="true"/></Skill>
    </SkillSet>
    <SkillSet title="ACT 3">
      <Skill label="Main">
        <Gem nameSpec="Essence Drain" enabled="true"/>
        <Gem nameSpec="Controlled Destruction" enabled="true"/>
      </Skill>
    </SkillSet>
  </Skills>
  <Items>
    <Item id="1">Rarity: RARE
Foo Wand
Withered Wand</Item>
    <ItemSet title="ACT 1"><Slot name="Weapon 1" itemId="1"/></ItemSet>
    <ItemSet title="ENDGAME (LOW LIFE)">
      <Slot name="Weapon 1" itemId="1"/><Slot name="Helmet" itemId="1"/>
    </ItemSet>
  </Items>
</PathOfBuilding2>"""


class TestTierTiming(unittest.TestCase):
    def test_tier_to_level_uses_curve(self):
        from guide2pob.buildfile import tier_to_level, _GEM_REQ_CURVE_FALLBACK as C
        self.assertEqual(tier_to_level(0, C), 1)   # no tier -> level 1
        self.assertEqual(tier_to_level(1, C), 1)   # C[0]
        self.assertEqual(tier_to_level(3, C), 6)   # C[2] (Essence Drain tier)
        self.assertEqual(tier_to_level(4, C), 10)  # C[3] (Ravenous Swarm tier)
        self.assertEqual(tier_to_level(5, C), 14)  # C[4] (Bonestorm tier)

    def test_tier_clamped_beyond_curve(self):
        from guide2pob.buildfile import tier_to_level
        self.assertEqual(tier_to_level(99, [1, 3, 6]), 6)

    def test_build_uses_tier_for_gem_interval(self):
        # A Tier-5 gem with no variant level should start at the Tier level (14).
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, 'Data'))
        with open(os.path.join(d, 'Data', 'Gems.lua'), 'w', encoding='utf-8') as f:
            f.write('return {\n["Metadata/Items/Gems/SkillGemBoneblast"] = {\n'
                    '\tname = "Boneblast",\n\tTier = 5,\n\t},\n}\n')
        pob = types.SimpleNamespace(path=d)
        parsed = {
            'class_name': 'Witch', 'ascend_name': 'Lich', 'level': 90,
            'node_ids': [], 'skill_groups': [{'label': 'M', 'gems': ['Boneblast']}],
            'slot_map': {}, 'items_by_id': {},
        }
        doc = build_dotbuild(parsed, pob=pob, node_id_map={}, name='b')
        self.assertEqual(doc['skills'][0]['level_interval'], [14, 100])


class TestVariantStartLevel(unittest.TestCase):
    def test_acts(self):
        from guide2pob.buildfile import variant_start_level as v
        self.assertEqual(v('ACT 1'), 1)
        self.assertEqual(v('ACT 2'), 12)
        self.assertEqual(v('ACT 3'), 22)
        self.assertEqual(v('ACT 4 - Endgame'), 33)  # act number wins

    def test_endgame(self):
        from guide2pob.buildfile import variant_start_level as v
        self.assertEqual(v('ENDGAME (LOW LIFE)'), 65)
        self.assertEqual(v('Maps'), 65)


class TestProgression(unittest.TestCase):
    def test_gem_first_appearance_levels(self):
        from guide2pob.buildfile import parse_pob_progression
        p = parse_pob_progression(MULTI_VARIANT_XML)
        # Essence Drain is in ACT 1 -> level 1; Controlled Destruction first in ACT 3 -> 22
        self.assertEqual(p['gem_levels']['essence drain'], 1)
        self.assertEqual(p['gem_levels']['controlled destruction'], 22)

    def test_item_first_appearance_levels(self):
        from guide2pob.buildfile import parse_pob_progression
        p = parse_pob_progression(MULTI_VARIANT_XML)
        self.assertEqual(p['item_levels']['Weapon 1'], 1)        # ACT 1
        self.assertEqual(p['item_levels']['Helmet'], 65)         # ENDGAME only

    def test_build_dotbuild_uses_gem_levels(self):
        from guide2pob.buildfile import parse_pob_progression
        p = parse_pob_progression(MULTI_VARIANT_XML)
        pob = _fake_pob_with_gems()
        doc = build_dotbuild(p, pob=pob,
                             node_id_map={'100': 'a', '200': 'b', '300': 'c'},
                             name='b')
        sk = doc['skills'][0]
        self.assertEqual(sk['level_interval'], [1, 100])         # ED from level 1
        # the support (Controlled Destruction) first appears in ACT 3 -> 22
        self.assertEqual(sk['support_skills'][0]['level_interval'], [22, 100])

    def test_item_level_interval_in_inventory(self):
        from guide2pob.buildfile import parse_pob_progression
        p = parse_pob_progression(MULTI_VARIANT_XML)
        doc = build_dotbuild(p, node_id_map={'100': 'a'}, name='b')
        inv = {e['inventory_id']: e for e in doc['inventory_slots']}
        self.assertEqual(inv['Weapon1']['level_interval'], [1, 100])
        self.assertEqual(inv['Helm']['level_interval'], [65, 100])


class TestCliEmitBuildfile(unittest.TestCase):
    def _args(self, out_dir):
        return types.SimpleNamespace(
            buildfile=True, buildfile_dir=out_dir, _pob=None,
            source='https://mobalytics.gg/poe-2/builds/x',
            _node_id_map_cache={'100': 'strength1', '200': 'dexterity1'})

    def test_emits_named_like_saved_xml(self):
        from guide2pob.cli import _emit_buildfile
        out = tempfile.mkdtemp()
        args = self._args(out)
        saved_xml = os.path.join(tempfile.mkdtemp(), 'My Cool Build.xml')
        path = _emit_buildfile(SAMPLE_XML, saved_xml, args)
        self.assertIsNotNone(path)
        self.assertEqual(os.path.basename(path), 'My Cool Build.build')
        with open(path, encoding='utf-8') as f:
            doc = json.load(f)
        self.assertEqual(doc['name'], 'My Cool Build')
        self.assertEqual(doc['passives'], [{'id': 'strength1'}, {'id': 'dexterity1'}])

    def test_failure_is_non_fatal(self):
        from guide2pob.cli import _emit_buildfile
        args = self._args(tempfile.mkdtemp())
        # Garbage XML -> parse fails -> returns None, does not raise.
        self.assertIsNone(_emit_buildfile('<not valid', '/tmp/x.xml', args))

    def test_node_map_cached(self):
        from guide2pob.cli import _node_id_map
        args = types.SimpleNamespace(_node_id_map_cache={'1': 'a'})
        # Pre-seeded cache is returned without touching the network.
        self.assertEqual(_node_id_map(args), {'1': 'a'})


class TestCliFlags(unittest.TestCase):
    def test_buildfile_default_on(self):
        from guide2pob.cli import _build_parser
        args = _build_parser().parse_args(['http://x'])
        self.assertTrue(args.buildfile)

    def test_no_buildfile_flag(self):
        from guide2pob.cli import _build_parser
        args = _build_parser().parse_args(['--no-buildfile', 'http://x'])
        self.assertFalse(args.buildfile)


if __name__ == '__main__':
    unittest.main()
