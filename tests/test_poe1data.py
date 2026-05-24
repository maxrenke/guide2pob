import unittest

from guide2pob.poe1data import resolve_class, CLASSES, ASCENDANCY_TO_CLASS


class TestPoe1Data(unittest.TestCase):

    def test_witch_occultist(self):
        info = resolve_class(ascendancy='Occultist')
        self.assertEqual(info['class_name'], 'Witch')
        self.assertEqual(info['class_id'], 3)
        self.assertEqual(info['ascend_id'], 3)
        self.assertEqual(info['ascend_name'], 'Occultist')

    def test_ascendancy_alone_resolves_class(self):
        info = resolve_class(ascendancy='Deadeye')
        self.assertEqual(info['class_name'], 'Ranger')
        self.assertEqual(info['class_id'], 2)

    def test_class_only_no_ascendancy(self):
        info = resolve_class(class_name='Shadow')
        self.assertEqual(info['ascend_id'], 0)
        self.assertEqual(info['ascend_name'], 'None')

    def test_case_insensitive(self):
        info = resolve_class(ascendancy='juggernaut')
        self.assertEqual(info['class_name'], 'Marauder')

    def test_unknown_ascendancy_raises(self):
        with self.assertRaises(ValueError):
            resolve_class(ascendancy='Lich')  # PoE2 only

    def test_missing_inputs_raises(self):
        with self.assertRaises(ValueError):
            resolve_class()

    def test_every_class_has_unique_ids(self):
        ids = [info['classId'] for info in CLASSES.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ascendancy_to_class_index_consistent(self):
        for asc_name, cls_name in ASCENDANCY_TO_CLASS.items():
            names = [a['name'] for a in CLASSES[cls_name]['ascendancies']]
            self.assertIn(asc_name, names)

    def test_all_seven_classes_present(self):
        expected = {'Scion', 'Marauder', 'Ranger', 'Witch',
                    'Duelist', 'Templar', 'Shadow'}
        self.assertEqual(set(CLASSES.keys()), expected)


if __name__ == '__main__':
    unittest.main()
