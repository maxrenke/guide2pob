"""Tests for cli.py helpers that don't require network or PoB installs."""
import unittest

from guide2pob.cli import _make_notes, _detect_game, _label_slug, _print_info


class TestDetectGame(unittest.TestCase):

    def test_poe2_url(self):
        self.assertEqual(
            _detect_game('https://mobalytics.gg/poe-2/builds/some-build'),
            'poe2')

    def test_poe1_url(self):
        self.assertEqual(
            _detect_game('https://mobalytics.gg/poe/builds/some-build'),
            'poe1')

    def test_unknown_defaults_to_poe2(self):
        self.assertEqual(_detect_game('/local/file.html'), 'poe2')

    def test_poe2_short_path(self):
        self.assertEqual(
            _detect_game('https://mobalytics.gg/poe2/builds/x'), 'poe2')


class TestMakeNotes(unittest.TestCase):

    def test_includes_name_and_url(self):
        notes = _make_notes('My Build', 'https://example.com', [])
        self.assertIn('My Build', notes)
        self.assertIn('https://example.com', notes)

    def test_includes_variant_labels(self):
        notes = _make_notes('Build', 'https://example.com',
                            ['Leveling', 'Endgame'])
        self.assertIn('Variants:', notes)
        self.assertIn('0: Leveling', notes)
        self.assertIn('1: Endgame', notes)

    def test_falls_back_to_variant_index_when_label_none(self):
        notes = _make_notes('Build', 'https://example.com', [None, 'Endgame'])
        self.assertIn('0: Variant 0', notes)
        self.assertIn('1: Endgame', notes)

    def test_no_variant_section_when_all_labels_none(self):
        notes = _make_notes('Build', 'https://example.com', [None, None])
        self.assertNotIn('Variants:', notes)

    def test_includes_description(self):
        notes = _make_notes('Build', 'https://example.com', [],
                            description='A short summary.')
        self.assertIn('A short summary.', notes)

    def test_description_omitted_when_matches_name(self):
        # Duplicate description adds no value.
        notes = _make_notes('My Build', 'https://example.com', [],
                            description='My Build')
        # Should appear only once (as the name, not repeated as description).
        self.assertEqual(notes.count('My Build'), 1)

    def test_includes_guide_html(self):
        html = (
            '<div class="lexical-rich-text-content">'
            '<p>Use Essence Drain to clear packs.</p>'
            '</div></div>'
        )
        notes = _make_notes('Build', 'https://example.com', [], html=html)
        self.assertIn('Use Essence Drain to clear packs.', notes)

    def test_no_html_still_works(self):
        notes = _make_notes('Build', 'https://example.com', [], html=None)
        self.assertIn('Build', notes)


class TestLabelSlug(unittest.TestCase):

    def test_simple_label(self):
        self.assertEqual(_label_slug('Endgame'), 'Endgame')

    def test_spaces_become_hyphens(self):
        self.assertEqual(_label_slug('Early Waystones'), 'Early-Waystones')

    def test_special_chars_stripped(self):
        # Parentheses, slashes, etc. removed; spaces -> hyphens
        self.assertEqual(_label_slug('Act 1-3'), 'Act-1-3')
        result = _label_slug('Build (v2)!')
        self.assertNotIn('(', result)
        self.assertNotIn(')', result)
        self.assertNotIn('!', result)

    def test_empty_or_none_returns_none(self):
        self.assertIsNone(_label_slug(''))
        self.assertIsNone(_label_slug(None))

    def test_capped_at_40_chars(self):
        long = 'A' * 50
        self.assertLessEqual(len(_label_slug(long)), 40)


class TestPrintInfo(unittest.TestCase):
    """_print_info should emit readable build metadata to stdout."""

    def _make_doc(self):
        return {
            'name': 'My PoE2 Build',
            'buildVariants': {'values': [
                {'id': 'v1', 'passiveTree': {
                    'mainTree': {'selectedSlugs': ['node-1', 'node-2']},
                    'ascendancyTree': {'selectedSlugs': ['node-3']},
                }},
                {'id': 'v2', 'passiveTree': {
                    'mainTree': {'selectedSlugs': ['node-4']},
                    'ascendancyTree': {'selectedSlugs': []},
                }},
            ]},
        }

    def _run_info(self, doc, html=None, source='https://mobalytics.gg/poe-2/builds/my-build'):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_info(doc, html, source)
        return buf.getvalue()

    def test_includes_name_and_slug(self):
        out = self._run_info(self._make_doc())
        self.assertIn('My PoE2 Build', out)
        self.assertIn('my-build', out)

    def test_includes_game(self):
        out = self._run_info(self._make_doc())
        self.assertIn('PoE2', out)

    def test_includes_variant_count(self):
        out = self._run_info(self._make_doc())
        self.assertIn('2', out)

    def test_includes_node_counts(self):
        out = self._run_info(self._make_doc())
        self.assertIn('2 main', out)   # variant 0: 2 main nodes
        self.assertIn('1 main', out)   # variant 1: 1 main node


class TestFallbackUniqueBases(unittest.TestCase):

    def test_known_unique_resolved_without_pob(self):
        from guide2pob.convert import _item_text
        item = {'isUnique': True, 'name': 'Tabula Rasa',
                'explicitDescriptions': []}
        text = _item_text(item, pob=None)
        lines = text.split('\n')
        # Third line should be the resolved base, not "Tabula Rasa" repeated.
        self.assertEqual(lines[2], 'Simple Robe')

    def test_unknown_unique_falls_back_to_name(self):
        from guide2pob.convert import _item_text
        item = {'isUnique': True, 'name': 'Some Unknown Unique',
                'explicitDescriptions': []}
        text = _item_text(item, pob=None)
        lines = text.split('\n')
        self.assertEqual(lines[2], 'Some Unknown Unique')

    def test_pob_data_takes_priority_over_fallback(self):
        from guide2pob.convert import _item_text

        class _FakePob:
            unique_bases = {'tabula rasa': 'Custom Base From PoB'}
            gems = {}

        item = {'isUnique': True, 'name': 'Tabula Rasa',
                'explicitDescriptions': []}
        text = _item_text(item, pob=_FakePob())
        self.assertIn('Custom Base From PoB', text)


if __name__ == '__main__':
    unittest.main()
