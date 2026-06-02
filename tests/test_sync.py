import unittest

from guide2pob.sync import (
    extract_user_notes, inject_user_notes, USER_NOTES_BEGIN, USER_NOTES_END,
)


def _xml(notes):
    return f'<PathOfBuilding2><Build/><Notes>{notes}</Notes></PathOfBuilding2>'


BLOCK = f"{USER_NOTES_BEGIN}\nlevel as grenades, ascend, then tame.\n{USER_NOTES_END}"


class TestExtractUserNotes(unittest.TestCase):
    def test_present(self):
        xml = _xml(f"Build title\nhttp://x\n\n{BLOCK}\n")
        self.assertEqual(extract_user_notes(xml), BLOCK)

    def test_absent(self):
        self.assertIsNone(extract_user_notes(_xml("just source notes")))

    def test_no_notes_element(self):
        self.assertIsNone(extract_user_notes('<PathOfBuilding2/>'))


class TestInjectUserNotes(unittest.TestCase):
    def test_append_when_absent(self):
        xml = _xml("fresh source notes")
        out = inject_user_notes(xml, BLOCK)
        self.assertIn(BLOCK, out)
        self.assertIn("fresh source notes", out)  # source notes kept
        self.assertEqual(out.count(USER_NOTES_BEGIN), 1)

    def test_replace_when_present(self):
        old_block = f"{USER_NOTES_BEGIN}\nOLD\n{USER_NOTES_END}"
        xml = _xml(f"src\n{old_block}")
        out = inject_user_notes(xml, BLOCK)
        self.assertIn("level as grenades", out)
        self.assertNotIn("OLD", out)
        self.assertEqual(out.count(USER_NOTES_BEGIN), 1)

    def test_noop_without_block(self):
        xml = _xml("src")
        self.assertEqual(inject_user_notes(xml, None), xml)

    def test_noop_without_notes_element(self):
        xml = '<PathOfBuilding2/>'
        self.assertEqual(inject_user_notes(xml, BLOCK), xml)


class TestRoundTrip(unittest.TestCase):
    def test_preserve_across_regeneration(self):
        # old build has user notes; fresh scrape doesn't -> carry it over
        old = _xml(f"Old title\nhttp://x\n\n{BLOCK}\n")
        fresh = _xml("New title\nhttp://x\n\nFresh source guide text")
        block = extract_user_notes(old)
        merged = inject_user_notes(fresh, block)
        self.assertIn("Fresh source guide text", merged)   # new source content
        self.assertIn("level as grenades", merged)         # preserved user notes
        # round-trip is idempotent
        again = inject_user_notes(merged, extract_user_notes(merged))
        self.assertEqual(again.count(USER_NOTES_BEGIN), 1)


if __name__ == '__main__':
    unittest.main()
