"""Tests for cli.py helpers that don't require network or PoB installs."""
import unittest

from moba2pob.cli import _make_notes, _detect_game


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


if __name__ == '__main__':
    unittest.main()
