import unittest
from guide2pob.scrape_poeninja import (
    _read_varint, _decode_msg, _try_nested,
    _dim_entries, _dim_hash, _resolve_ids,
)


class TestReadVarint(unittest.TestCase):

    def test_single_byte(self):
        self.assertEqual(_read_varint(b'\x01', 0), (1, 1))
        self.assertEqual(_read_varint(b'\x7f', 0), (127, 1))

    def test_multibyte(self):
        # 300 = 0b100101100 -> 0xAC 0x02
        val, pos = _read_varint(b'\xac\x02', 0)
        self.assertEqual(val, 300)
        self.assertEqual(pos, 2)

    def test_with_offset(self):
        buf = b'\x00\x01\x02'
        val, pos = _read_varint(buf, 1)
        self.assertEqual(val, 1)
        self.assertEqual(pos, 2)


class TestTryNested(unittest.TestCase):

    def test_sha1_hash_not_decoded_as_nested(self):
        # SHA1 hashes starting with '2' (0x32 = field 6, wt=2) used to be
        # misinterpreted as nested messages because 0x32 is a valid tag byte.
        hash_str = b'2b1b2470a9ae0e30686d171e026bf8e6100da828'
        result = _try_nested(hash_str)
        self.assertIsNone(result)

    def test_sha1_hash_decoded_as_string(self):
        hash_str = b'2b1b2470a9ae0e30686d171e026bf8e6100da828'
        msg = _decode_msg(b'\x12\x28' + hash_str)  # field 2, len=40, data
        self.assertEqual(msg[2], ['2b1b2470a9ae0e30686d171e026bf8e6100da828'])

    def test_real_nested_decoded(self):
        # field 1 (varint) = 42, field 2 (varint) = 7
        # tag field1=wt0: 0x08, val=42; tag field2=wt0: 0x10, val=7
        data = b'\x08\x2a\x10\x07'
        result = _try_nested(data)
        self.assertIsNotNone(result)
        self.assertEqual(result[1], [42])
        self.assertEqual(result[2], [7])

    def test_empty_bytes_returns_none(self):
        self.assertIsNone(_try_nested(b''))


class TestDecodeMsg(unittest.TestCase):

    def test_varint_field(self):
        # field 1, wire type 0, value 5
        msg = _decode_msg(b'\x08\x05')
        self.assertEqual(msg[1], [5])

    def test_string_field(self):
        # field 1, wire type 2, 'hello'
        msg = _decode_msg(b'\x0a\x05hello')
        self.assertEqual(msg[1], ['hello'])

    def test_repeated_fields(self):
        # two field-1 varints: 1 and 2
        msg = _decode_msg(b'\x08\x01\x08\x02')
        self.assertEqual(msg[1], [1, 2])

    def test_strict_rejects_overflow(self):
        # field 1, wire type 2, claims length=100 but only 3 bytes follow
        with self.assertRaises(ValueError):
            _decode_msg(b'\x0a\x64abc', strict=True)

    def test_non_strict_tolerates_overflow(self):
        # same as above but strict=False - should not raise
        msg = _decode_msg(b'\x0a\x64abc', strict=False)
        self.assertIn(1, msg)


class TestDimHelpers(unittest.TestCase):

    _RESULT = {
        2: [
            {1: ['class'], 2: ['class'], 3: [
                {1: [1], 2: [500]},
                {1: [2], 2: [300]},
            ]},
            {1: ['skills'], 2: ['gem'], 3: [
                {1: [1], 2: [1000]},
                {1: [3], 2: [200]},
            ]},
            {1: ['keypassives'], 2: ['keypassive'], 3: []},
        ],
        6: [
            {1: ['class'], 2: ['aabbcc']},
            {1: ['gem'], 2: ['ddeeff']},
            {1: ['keypassive'], 2: ['112233']},
        ],
    }

    def test_dim_entries_by_internal_name(self):
        entries = _dim_entries(self._RESULT, 'class')
        self.assertEqual(sorted(entries), [(1, 500), (2, 300)])

    def test_dim_entries_by_display_name(self):
        entries = _dim_entries(self._RESULT, 'gem')
        self.assertEqual(sorted(entries), [(1, 1000), (3, 200)])

    def test_dim_entries_internal_name_skills(self):
        entries = _dim_entries(self._RESULT, 'skills')
        self.assertEqual(sorted(entries), [(1, 1000), (3, 200)])

    def test_dim_hash_by_display_name(self):
        h = _dim_hash(self._RESULT, 'skills')
        self.assertEqual(h, 'ddeeff')

    def test_dim_hash_keypassives(self):
        h = _dim_hash(self._RESULT, 'keypassives')
        self.assertEqual(h, '112233')

    def test_dim_hash_missing(self):
        self.assertIsNone(_dim_hash(self._RESULT, 'nonexistent'))


class TestResolveIds(unittest.TestCase):

    def test_basic_mapping(self):
        names = ['Alpha', 'Beta', 'Gamma']
        result = _resolve_ids([(1, 100), (3, 50)], names)
        self.assertEqual(result, {'Alpha': 100, 'Gamma': 50})

    def test_out_of_range_ignored(self):
        names = ['Alpha']
        result = _resolve_ids([(0, 10), (5, 20)], names)
        self.assertEqual(result, {})

    def test_empty(self):
        self.assertEqual(_resolve_ids([], ['A', 'B']), {})


if __name__ == '__main__':
    unittest.main()
