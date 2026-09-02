import unittest

from scripts.build_boamp_market_observations import build
from scripts.fetch_boamp_data import facts_hash


def facts():
    return {
        "schema": "lawradar-opportunity-facts-v1", "signal_id": "signal:1",
        "title": "Service test", "keywords": ["service test"], "affected_scope": ["France"],
        "legal": {"jurisdiction": "FR", "text_status": "PUBLISHED", "proof_status": "VERIFIED", "effective_date": None, "affected_scope": ["France"]},
        "requirements": {"required_capabilities": [], "required_authorizations": [], "dependencies": [], "minimum_startup_capital_eur": None, "estimated_time_to_market_weeks": None, "evidence_status": "MISSING"},
    }


def boamp(records, status="COMPLETED", errors=None):
    current = facts()
    return {
        "schema": "lawradar-market-demand-boamp-v1", "signal_id": "signal:1", "signal_hash": facts_hash(current),
        "collected_at_utc": "2026-09-02T12:00:00Z", "collection_status": status,
        "observations": records, "errors": errors or [],
    }


class BuildBoampMarketObservationsTests(unittest.TestCase):
    def test_converts_a_traceable_public_notice(self):
        result = build(facts(), boamp([{"id": "1", "title": "Prestation de service test", "buyer": "Ville A", "url": "https://boamp.test/1"}]))
        self.assertEqual(result["collection_status"], "COMPLETED")
        self.assertEqual(result["observations"][0]["actor"], "Ville A")
        self.assertEqual(result["observations"][0]["observation_type"], "PUBLIC_PROCUREMENT")

    def test_untraceable_notice_is_unresolved_not_market_evidence(self):
        result = build(facts(), boamp([{"id": "1", "title": "Prestation de service test", "url": None}]))
        self.assertEqual(result["collection_status"], "UNRESOLVED")
        self.assertEqual(result["observations"], [])
