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

    def test_rejects_a_delivery_missing_a_candidate_decision(self):
        with self.assertRaises(ValueError):
            build_dossier(motor_input(), delivery("jorf:other"), run_manifest())
