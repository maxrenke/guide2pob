import unittest

from guide2pob.scrape import (
    _extract_preloaded_state, _find_build_document, parse_build,
    variant_labels, slug_from_url, guide_text, build_description, ScrapeError)
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


class TestFindBuildDocumentProfileUrl(unittest.TestCase):
    """_find_build_document must handle the profile-URL key too."""

    def _make_state(self, key):
        return {key: {
            'data': {'data': {
                'name': 'Profile Build',
                'buildVariants': {'values': [{'id': 'v1'}]},
            }}
        }}

    def test_slug_key(self):
        doc = _find_build_document(self._make_state('userGeneratedDocumentBySlug'))
        self.assertIsNotNone(doc)
        self.assertEqual(doc['name'], 'Profile Build')

    def test_slugified_name_key(self):
        doc = _find_build_document(
            self._make_state('userGeneratedDocumentBySlugifiedName'))
        self.assertIsNotNone(doc)
        self.assertEqual(doc['name'], 'Profile Build')


class TestBuildDescription(unittest.TestCase):

    _HTML = (
        '<html><head>'
        '<meta property="og:description" content="A great PoE2 build guide.">'
        '</head><body></body></html>'
    )

    def test_extracts_og_description(self):
        desc = build_description(self._HTML)
        self.assertEqual(desc, 'A great PoE2 build guide.')

    def test_returns_none_when_absent(self):
        self.assertIsNone(build_description('<html></html>'))

    def test_returns_none_for_no_html(self):
        self.assertIsNone(build_description(None))


class TestGuideText(unittest.TestCase):

    _HTML = (
        '<div class="lexical-rich-text-content">'
        '<h4><b>Build Overview</b></h4>'
        '<p>This build uses Essence Drain + Contagion.</p>'
        '<ul><li>Great clear</li><li>Easy to scale</li></ul>'
        '</div></div>'
        '<div class="lexical-rich-text-content">'
        '<p>Pros: very fast</p>'
        '</div></div>'
    )

    def test_extracts_text_from_blocks(self):
        text = guide_text(self._HTML)
        self.assertIn('Build Overview', text)
        self.assertIn('Essence Drain + Contagion', text)
        self.assertIn('Great clear', text)

    def test_multiple_blocks_joined_by_blank_line(self):
        text = guide_text(self._HTML)
        self.assertIn('\n\n', text)
        self.assertIn('Pros: very fast', text)

    def test_strips_html_tags(self):
        text = guide_text(self._HTML)
        self.assertNotIn('<p>', text)
        self.assertNotIn('<b>', text)
        self.assertNotIn('<li>', text)

    def test_returns_empty_string_for_no_html(self):
        self.assertEqual(guide_text(None), '')

    def test_returns_empty_string_when_no_blocks(self):
        self.assertEqual(guide_text('<html><body>no blocks</body></html>'), '')


if __name__ == '__main__':
    unittest.main()
