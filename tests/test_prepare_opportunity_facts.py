import unittest

from scripts.prepare_opportunity_facts import extract


def facts(signal_id):
    return {
        "schema": "lawradar-opportunity-facts-v1", "signal_id": signal_id,
        "title": "Signal test", "keywords": ["signal test"], "affected_scope": ["France"],
        "legal": {"jurisdiction": "FR", "text_status": "PUBLISHED", "proof_status": "VERIFIED", "effective_date": None, "affected_scope": ["France"]},
        "requirements": {"required_capabilities": [], "required_authorizations": [], "dependencies": [], "minimum_startup_capital_eur": None, "estimated_time_to_market_weeks": None, "evidence_status": "MISSING"},
    }


class PrepareOpportunityFactsTests(unittest.TestCase):
    def test_extracts_only_facts_bound_to_the_requested_retained_signal(self):
        signal_id = "signal:current"
        dossier = {
            "schema": "lawradar-universal-signal-v1",
            "signals": [{
                "id": signal_id,
                "radar": {"status": "RETAINED"},
                "opportunity_facts": facts(signal_id),
            }],
        }
        self.assertEqual(extract(dossier, signal_id)["signal_id"], signal_id)

    def test_rejects_facts_linked_to_another_signal(self):
        dossier = {
            "schema": "lawradar-universal-signal-v1",
            "signals": [{
                "id": "signal:current",
                "radar": {"status": "RETAINED"},
                "opportunity_facts": facts("signal:other"),
            }],
        }
        with self.assertRaises(ValueError):
            extract(dossier, "signal:current")
