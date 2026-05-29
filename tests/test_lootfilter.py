"""Tests for build-customized loot-filter generation (lootfilter.py)."""
import os
import tempfile
import unittest
import zipfile

from guide2pob import lootfilter as lf


BASE_FILTER = """# NeverSink base
#===============
# [[0100]] OVERRIDE AREA 1 - Override ALL rules here
#===============

# [[0100]] Gold
# !! Waypoint c0.start : "Start - Override ALL rules"

Show
\tClass "Gold"
"""

BUILD_XML = """<?xml version="1.0"?>
<PathOfBuilding2>
  <Build className="Witch" ascendClassName="Lich" level="90"/>
  <Skills>
    <SkillSet><Skill label="Main">
      <Gem nameSpec="Essence Drain" enabled="true"/>
    </Skill></SkillSet>
  </Skills>
</PathOfBuilding2>"""

MINION_XML = BUILD_XML.replace('Essence Drain', 'Raise Zombie')


class TestClassify(unittest.TestCase):
    def test_class_default(self):
        self.assertEqual(lf.classify('Witch'), 'caster')
        self.assertEqual(lf.classify('Warrior'), 'attack_armour')
        self.assertEqual(lf.classify('Ranger'), 'attack_bow')

    def test_minion_detected_from_skills(self):
        skills = [{'label': 'Minions', 'gems': ['Raise Zombie', 'Minion Damage']}]
        self.assertEqual(lf.classify('Witch', 'Lich', skills), 'minion')

    def test_override_wins(self):
        self.assertEqual(lf.classify('Witch', None, None, override='crossbow'), 'crossbow')

    def test_unknown_class_defaults_caster(self):
        self.assertEqual(lf.classify('Unknown'), 'caster')


class TestComposeBlock(unittest.TestCase):
    def test_caster_block(self):
        b = lf.compose_block('caster')
        self.assertIn('Class "Wands" "Sceptres" "Staves" "Foci"', b)
        self.assertIn('Rarity Rare', b)
        self.assertIn('Show', b)

    def test_unknown_archetype_raises(self):
        with self.assertRaises(ValueError):
            lf.compose_block('nope')


class TestInjectBlock(unittest.TestCase):
    def test_inserts_after_anchor(self):
        out = lf.inject_block(BASE_FILTER, 'Show\n\tClass "X"')
        lines = out.splitlines()
        ai = next(i for i, l in enumerate(lines) if 'Waypoint c0.start' in l)
        bi = next(i for i, l in enumerate(lines) if lf.BEGIN.strip() in l)
        self.assertGreater(bi, ai)               # block sits after the anchor
        self.assertEqual(out.count(lf.BEGIN), 1)

    def test_idempotent(self):
        once = lf.inject_block(BASE_FILTER, 'Show\n\tClass "X"')
        twice = lf.inject_block(once, 'Show\n\tClass "Y"')
        self.assertEqual(twice.count(lf.BEGIN), 1)
        self.assertIn('Class "Y"', twice)
        self.assertNotIn('Class "X"', twice)

    def test_no_anchor_inserts_at_top(self):
        out = lf.inject_block('Show\n\tClass "Gold"\n', 'Show\n\tClass "Z"')
        self.assertEqual(out.count(lf.BEGIN), 1)
        self.assertIn('Class "Z"', out)


class TestPickBase(unittest.TestCase):
    def test_matches_strictness_index(self):
        installed = ['x_0_Soft.filter', 'x_3_Strict.filter', 'x_6_Uber.filter']
        self.assertTrue(lf.pick_base('/d', installed, 3).endswith('x_3_Strict.filter'))

    def test_safe_filename(self):
        self.assertEqual(lf.safe_filename('a/b:c'), 'a_b_c')
        self.assertEqual(lf.safe_filename(''), 'build')


class TestGenerate(unittest.TestCase):
    def _setup_dir(self, base_name='base_3_Strict.filter'):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, base_name), 'w', encoding='utf-8') as f:
            f.write(BASE_FILTER)
        return d

    def _build_file(self, xml=BUILD_XML):
        fd, p = tempfile.mkstemp(suffix='.xml')
        os.close(fd)
        open(p, 'w', encoding='utf-8').write(xml)
        return p

    def test_generate_reuses_installed_base(self):
        d = self._setup_dir()
        r = lf.generate(build=self._build_file(), filter_dir=d, strictness=3)
        self.assertEqual(r['archetype'], 'caster')
        self.assertEqual(r['class'], 'Witch')
        self.assertTrue(os.path.isfile(r['output']))
        out = open(r['output'], encoding='utf-8').read()
        self.assertIn(lf.BEGIN, out)
        self.assertIn('Class "Wands"', out)
        # base is left untouched
        self.assertNotIn(lf.BEGIN, open(r['base'], encoding='utf-8').read())

    def test_generate_minion_build(self):
        d = self._setup_dir()
        r = lf.generate(build=self._build_file(MINION_XML), filter_dir=d, strictness=3)
        self.assertEqual(r['archetype'], 'minion')

    def test_generate_with_zip_backs_up_and_installs(self):
        d = tempfile.mkdtemp()
        # an existing old filter that should be backed up
        open(os.path.join(d, 'old_3_Strict.filter'), 'w').write('# old\n')
        # a base zip
        zpath = os.path.join(tempfile.mkdtemp(), 'base.zip')
        with zipfile.ZipFile(zpath, 'w') as z:
            z.writestr('new_3_Strict.filter', BASE_FILTER)
        r = lf.generate(zip_path=zpath, build=self._build_file(),
                        filter_dir=d, strictness=3)
        self.assertEqual(r['backed_up'], ['old_3_Strict.filter'])
        self.assertIn('new_3_Strict.filter', r['installed'])
        # old filter moved into a backup subfolder, not left at top level
        self.assertFalse(os.path.isfile(os.path.join(d, 'old_3_Strict.filter')))
        self.assertTrue(any(n.startswith('_old_filters_') for n in os.listdir(d)))

    def test_generate_no_base_raises(self):
        with self.assertRaises(FileNotFoundError):
            lf.generate(build=self._build_file(), filter_dir=tempfile.mkdtemp())


if __name__ == '__main__':
    unittest.main()
