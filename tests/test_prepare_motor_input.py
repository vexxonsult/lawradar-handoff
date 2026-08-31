import unittest

from scripts.prepare_motor_input import changed_records, requires_model


class PrepareMotorInputTests(unittest.TestCase):
    def test_jorf_only_returns_new_or_modified_documents(self):
        previous = {"editions": [{"documents": [{"text_id": "a", "title": "same"}]}]}
        current = {"editions": [{"documents": [
            {"text_id": "a", "title": "same"},
            {"text_id": "b", "title": "new"},
        ]}]}
        records = changed_records(current, previous, "JORF")
        self.assertEqual(records[0]["source_id"], "jorf:b")
        self.assertEqual(records[0]["change"], "NEW")

    def test_consultation_marks_modified_url_as_changed(self):
        previous = {"documents": [{"url": "u", "title": "old"}]}
        current = {"documents": [{"url": "u", "title": "new"}]}
        records = changed_records(current, previous, "CONSULTDD")
        self.assertEqual(records[0]["change"], "CHANGED")

    def test_does_not_invoke_model_without_supported_candidates(self):
        self.assertFalse(requires_model({"candidates": []}))
        self.assertTrue(requires_model({"candidates": [{"source_id": "jorf:x"}]}))
