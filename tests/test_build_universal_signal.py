import unittest

from scripts.build_universal_signal import build_dossier


def source(source_id="jorf:1"):
    return {
        "source_id": source_id,
        "source_kind": "JORF",
        "change": "NEW",
        "evidence": {"text_id": "1", "title": "Texte officiel", "interpretation": None},
    }


def delivery(source_id="jorf:1"):
    return {
        "schema": "lawradar-motor-delivery-v1",
        "run": {"coverage": "JORF seulement"},
        "opportunities": [{"source_id": source_id, "status": "UNRESOLVED", "reason": "Preuve insuffisante."}],
        "money_flows": [],
    }


def motor_input(source_id="jorf:1"):
    return {
        "schema": "lawradar-motor-input-v1",
        "report_date": "2026-09-01",
        "delta_changed_sources": ["jorf-summaries-latest.json"],
        "handled_source_files": ["jorf-summaries-latest.json"],
        "rules": "inconnu = UNRESOLVED",
        "candidates": [source(source_id)],
    }


def run_manifest():
    return {"schema": "lawradar-run-manifest-v1", "run": {"id": "42", "url": "https://example.test/42", "commit": "abc"}}


class UniversalSignalTests(unittest.TestCase):
    def test_builds_one_signal_with_empty_future_agent_slots(self):
        dossier = build_dossier(motor_input(), delivery(), run_manifest())
        self.assertEqual(dossier["schema"], "lawradar-universal-signal-v1")
        self.assertEqual(dossier["quality"]["unresolved_count"], 1)
        self.assertEqual(dossier["signals"][0]["enrichments"]["press"]["status"], "PENDING")
        self.assertIsNone(dossier["signals"][0]["enrichments"]["market"]["result"])

    def test_compacts_primary_evidence_without_its_full_text(self):
        input_data = motor_input()
        input_data["candidates"][0]["evidence"].update({
            "official_detail": {
                "official_title": "Titre officiel",
                "official_period": "Du 1er au 2 septembre",
                "official_text": "Texte primaire qui ne doit pas être dupliqué.",
            },
            "financial_evidence": [
                {"source_url": "https://example.test/piece.pdf", "page": 4, "excerpt": "Extrait vérifiable"},
                {"source_url": "https://example.test/piece.pdf", "page": 4, "excerpt": "Doublon"},
            ],
        })
        compact = build_dossier(input_data, delivery(), run_manifest())["signals"][0]["source"]["evidence"]
        self.assertEqual(compact["official"]["title"], "Titre officiel")
        self.assertNotIn("official_text", compact["official"])
        self.assertEqual(compact["evidence_excerpts"], [{
            "source_url": "https://example.test/piece.pdf", "page": 4, "excerpt": "Extrait vérifiable"
        }])

    def test_rejects_a_delivery_missing_a_candidate_decision(self):
        with self.assertRaises(ValueError):
            build_dossier(motor_input(), delivery("jorf:other"), run_manifest())
