import unittest

from scripts.prepare_motor_input import (
    changed_records,
    attach_jorf_excerpt,
    exclude_historical_jorf_records,
    exclude_routine_administration_records,
    requires_model,
)


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

    def test_excludes_a_historical_reappearance_outside_the_current_window(self):
        records = [
            {"source_id": "jorf:old", "evidence": {"publication_date": "1997-11-07"}},
            {"source_id": "jorf:current", "evidence": {"publication_date": "2026-09-02"}},
        ]
        accepted, excluded = exclude_historical_jorf_records(records, {"2026-09-02"})
        self.assertEqual([item["source_id"] for item in accepted], ["jorf:current"])
        self.assertEqual(excluded[0]["reason"], "HISTORICAL_REAPPEARANCE_OUTSIDE_CURRENT_COVERAGE")

    def test_excludes_routine_administration_with_a_trace(self):
        routine = {
            "source_id": "jorf:routine",
            "evidence": {"title": "Décision portant délégation de signature"},
        }
        relevant = {
            "source_id": "jorf:economy",
            "evidence": {"title": "Arrêté fixant les montants des aides aux entreprises"},
        }
        accepted, excluded = exclude_routine_administration_records([routine, relevant])
        self.assertEqual(accepted, [relevant])
        self.assertEqual(excluded[0]["source_id"], "jorf:routine")
        self.assertEqual(excluded[0]["reason"], "ROUTINE_PUBLIC_ADMINISTRATION_TITLE")

    def test_attaches_only_the_matching_official_excerpt(self):
        record = {"source_id": "jorf:1", "evidence": {"text_id": "1", "title": "Texte"}}
        result = attach_jorf_excerpt(record, {
            "1": {"text_id": "1", "content_status": "AVAILABLE", "official_text_excerpt": "Preuve officielle."}
        })
        self.assertEqual(result["evidence"]["official_text_excerpt"], "Preuve officielle.")
        self.assertNotIn("official_text_excerpt", record["evidence"])
