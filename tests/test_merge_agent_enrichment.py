import copy
import unittest

from scripts.merge_agent_enrichment import merge


def dossier():
    return {
        "schema": "lawradar-universal-signal-v1",
        "signals": [{
            "id": "signal:1",
            "source": {"title": "Preuve primaire"},
            "radar": {"status": "RETAINED", "reason": "Décision étayée"},
            "enrichments": {
                "press": {"status": "PENDING", "result": None},
                "demand": {"status": "PENDING", "result": None},
                "market": {"status": "PENDING", "result": None},
            },
        }],
        "money_flows": [{"id": "flow:1", "amount": "conditionnel"}],
    }


def press(signal_id="signal:1"):
    return {
        "schema": "lawradar-agent-enrichment-v1",
        "agent": "press",
        "signal_id": signal_id,
        "status": "NO_EVIDENCE",
        "observed_at_utc": "2026-09-02T12:00:00Z",
        "summary": "Aucune couverture vérifiée dans les sources autorisées.",
        "sources": [],
        "limitations": ["Périmètre de recherche défini par la future configuration."],
        "details": {},
        "score": None,
    }


class MergeAgentEnrichmentTests(unittest.TestCase):
    def test_updates_only_the_requested_empty_slot(self):
        original = dossier()
        merged = merge(original, press())
        self.assertEqual(original, dossier())
        self.assertEqual(merged["signals"][0]["source"], original["signals"][0]["source"])
        self.assertEqual(merged["signals"][0]["radar"], original["signals"][0]["radar"])
        self.assertEqual(merged["money_flows"], original["money_flows"])
        self.assertEqual(merged["signals"][0]["enrichments"]["press"]["status"], "NO_EVIDENCE")
        self.assertEqual(merged["signals"][0]["enrichments"]["demand"], original["signals"][0]["enrichments"]["demand"])

    def test_rejects_an_enrichment_for_an_unknown_signal(self):
        with self.assertRaises(ValueError):
            merge(dossier(), press("signal:unknown"))

    def test_rejects_a_score_without_a_versioned_method(self):
        candidate = press()
        candidate["score"] = 72
        with self.assertRaises(ValueError):
            merge(dossier(), candidate)

    def test_rejects_overwriting_a_completed_slot(self):
        completed = dossier()
        completed["signals"][0]["enrichments"]["press"] = {"status": "COMPLETED", "result": {"existing": True}}
        with self.assertRaises(ValueError):
            merge(completed, press())

    def test_allows_one_retry_after_unresolved_and_keeps_history(self):
        unresolved = dossier()
        first = press()
        first["status"] = "UNRESOLVED"
        unresolved["signals"][0]["enrichments"]["press"] = {"status": "UNRESOLVED", "result": first, "attempts": 1, "previous_results": []}
        second = press()
        second["status"] = "NO_EVIDENCE"
        merged = merge(unresolved, second)
        slot = merged["signals"][0]["enrichments"]["press"]
        self.assertEqual(slot["status"], "NO_EVIDENCE")
        self.assertEqual(slot["attempts"], 2)
        self.assertEqual(slot["previous_results"], [first])

    def test_rejects_a_second_retry_after_unresolved(self):
        unresolved = dossier()
        unresolved["signals"][0]["enrichments"]["press"] = {"status": "UNRESOLVED", "result": press(), "attempts": 2, "previous_results": []}
        with self.assertRaises(ValueError):
            merge(unresolved, press())
