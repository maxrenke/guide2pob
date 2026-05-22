import unittest

from moba2pob.scrape import (
    _extract_preloaded_state, _find_build_document, parse_build,
    variant_labels, slug_from_url, ScrapeError)
from tests.fixtures import sample_html


class TestPreloadedState(unittest.TestCase):

    def test_extracts_object(self):
        state = _extract_preloaded_state(sample_html())
        self.assertIn('poe2State', state)

    def test_missing_marker_raises(self):
        with self.assertRaises(ScrapeError):
            _extract_preloaded_state('<html>nothing here</html>')


class TestFindBuildDocument(unittest.TestCase):

    def test_locates_nested_document(self):
        state = _extract_preloaded_state(sample_html())
        doc = _find_build_document(state)
        self.assertIsNotNone(doc)
        self.assertIn('buildVariants', doc)
        self.assertEqual(doc['name'], 'Sample Build')

    def test_returns_none_when_absent(self):
        self.assertIsNone(_find_build_document({'unrelated': 'data'}))


class TestParseBuild(unittest.TestCase):

    def test_end_to_end(self):
        doc = parse_build(sample_html())
        self.assertEqual(doc['name'], 'Sample Build')


class TestVariantLabels(unittest.TestCase):

    def test_picks_first_short_text_node(self):
        html = sample_html()
        variants = [{'id': 'var-a'}]
        self.assertEqual(variant_labels(html, variants), ['Endgame'])

    def test_missing_id_returns_none(self):
        html = sample_html()
        variants = [{'id': 'does-not-exist'}, {}]
        self.assertEqual(variant_labels(html, variants), [None, None])

    def test_no_html_yields_padding(self):
        variants = [{'id': 'a'}, {'id': 'b'}]
        self.assertEqual(variant_labels(None, variants), [None, None])


class TestSlugFromUrl(unittest.TestCase):

    def test_extracts_slug(self):
        url = 'https://mobalytics.gg/poe-2/builds/ronarray-minion-lich'
        self.assertEqual(slug_from_url(url), 'ronarray-minion-lich')

    def test_returns_none_for_unrelated_url(self):
        self.assertIsNone(slug_from_url('https://example.com/'))


if __name__ == '__main__':
    unittest.main()
