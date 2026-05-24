import unittest

from guide2pob.upload import _to_urlsafe


class TestUrlSafe(unittest.TestCase):

    def test_replaces_plus_and_slash(self):
        self.assertEqual(
            _to_urlsafe('eNrl+abc/def='),
            'eNrl-abc_def=',
        )

    def test_strips_whitespace(self):
        self.assertEqual(_to_urlsafe('  abc\n'), 'abc')

    def test_pure_alnum_unchanged(self):
        self.assertEqual(_to_urlsafe('Endgame123'), 'Endgame123')


if __name__ == '__main__':
    unittest.main()
