import unittest

from guide2pob.poe2data import resolve_class, CLASSES, ASCENDANCY_TO_CLASS


class TestPoe2Data(unittest.TestCase):

    def test_witch_lich(self):
        info = resolve_class(ascendancy='Lich')
        self.assertEqual(info['class_name'], 'Witch')
        self.assertEqual(info['class_id'], 6)
        self.assertEqual(info['class_internal_id'], 1)
        self.assertEqual(info['ascend_id'], 3)
        self.assertEqual(info['ascend_internal_id'], 'Witch3')
        self.assertEqual(info['ascend_name'], 'Lich')

    def test_witch_infernalist_first_in_list(self):
        info = resolve_class(ascendancy='Infernalist')
        self.assertEqual(info['ascend_id'], 1)
        self.assertEqual(info['ascend_internal_id'], 'Witch1')

    def test_ascendancy_alone_resolves_class(self):
        info = resolve_class(ascendancy='Deadeye')
        self.assertEqual(info['class_name'], 'Ranger')

    def test_class_only_no_ascendancy(self):
        info = resolve_class(class_name='Witch')
        self.assertEqual(info['ascend_id'], 0)
        self.assertEqual(info['ascend_name'], 'None')

    def test_case_insensitive(self):
        info = resolve_class(ascendancy='lich')
        self.assertEqual(info['ascend_internal_id'], 'Witch3')

    def test_unknown_ascendancy_raises(self):
        with self.assertRaises(ValueError):
            resolve_class(ascendancy='Nonesuch')

    def test_missing_inputs_raises(self):
        with self.assertRaises(ValueError):
            resolve_class()

    def test_every_class_has_unique_ids(self):
        class_ids = [c['classId'] for c in CLASSES.values()]
        integer_ids = [c['integerId'] for c in CLASSES.values()]
        self.assertEqual(len(class_ids), len(set(class_ids)))
        self.assertEqual(len(integer_ids), len(set(integer_ids)))

    def test_ascendancy_to_class_index_matches_class_table(self):
        for name, cls in ASCENDANCY_TO_CLASS.items():
            self.assertIn(name, [a['name'] for a in CLASSES[cls]['ascendancies']])


if __name__ == '__main__':
    unittest.main()
