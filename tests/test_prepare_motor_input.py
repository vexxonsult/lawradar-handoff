import unittest

from scripts.prepare_motor_input import (
    changed_records,
    attach_jorf_excerpt,
    exclude_historical_jorf_records,
    exclude_routine_administration_records,
    requires_model,
)
from scripts.discover_opportunity_friction import assess, screen


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

    def test_routes_a_cross_sector_obligation_to_watch_without_claiming_an_opportunity(self):
        record = {
            "source_id": "jorf:energy", "source_kind": "JORF", "change": "NEW",
            "evidence": {"title": "Arrêté créant une obligation de déclaration", "content_status": "AVAILABLE"},
        }
        result = assess(record)
        self.assertEqual(result["status"], "WATCH_CANDIDATE")
        self.assertEqual(result["triggers"][0]["kind"], "LEGAL_OBLIGATION")
        self.assertEqual(result["recommended_enrichment"], ["PRESS", "DEMAND", "MARKET"])

    def test_routes_individual_licence_out_without_spending_a_model_call(self):
        record = {
            "source_id": "jorf:doctor", "source_kind": "JORF", "change": "NEW",
            "evidence": {"title": "Décision d'autorisation d'exercer la profession de médecin", "content_status": "AVAILABLE"},
        }
        candidates, excluded = screen([record])
        self.assertEqual(candidates, [])
        self.assertEqual(excluded[0]["reason"], "INDIVIDUAL_OR_INTERNAL_ACT_TITLE")

    def test_keeps_missing_primary_text_for_explicit_queue_audit(self):
        record = {
            "source_id": "jorf:missing", "source_kind": "JORF", "change": "NEW",
            "evidence": {"title": "Décret portant obligation", "content_status": "UNAVAILABLE"},
        }
        candidates, excluded = screen([record])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["discovery"]["status"], "PRIMARY_EVIDENCE_MISSING")
        self.assertEqual(excluded, [])

    def test_does_not_route_an_internal_public_operation_on_deadline_words_alone(self):
        record = {
            "source_id": "jorf:security", "source_kind": "JORF", "change": "NEW",
            "evidence": {
                "title": "Décret relatif à la visite officielle", "content_status": "AVAILABLE",
                "official_text_excerpt": "Les personnes sont soumises à une procédure. Entrée en vigueur immédiate.",
            },
        }
        candidates, excluded = screen([record])
        self.assertEqual(candidates, [])
        self.assertEqual(excluded[0]["reason"], "NO_ECONOMIC_FRICTION_EVIDENCE")
