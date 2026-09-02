import unittest
from datetime import UTC, datetime

from scripts.build_boamp_demand_enrichment import build as enrich
from scripts.build_boamp_demand_observations import build as observations, build_blocked
from scripts.fetch_boamp_data import facts_hash
from scripts.validate_demand_enrichment import validate


def facts():
    return {"schema": "lawradar-opportunity-facts-v1", "signal_id": "signal:1", "title": "Service test", "keywords": ["service test"], "affected_scope": ["France"], "legal": {"jurisdiction": "FR", "text_status": "PUBLISHED", "proof_status": "VERIFIED", "effective_date": None, "affected_scope": ["France"]}, "requirements": {"required_capabilities": [], "required_authorizations": [], "dependencies": [], "minimum_startup_capital_eur": None, "estimated_time_to_market_weeks": None, "evidence_status": "MISSING"}}


def boamp(records, status="COMPLETED"):
    current = facts()
    return {"schema": "lawradar-market-demand-boamp-v1", "signal_id": "signal:1", "signal_hash": facts_hash(current), "collected_at_utc": "2026-09-02T12:00:00+00:00", "collection_status": status, "observations": records, "errors": []}


class BoampDemandTests(unittest.TestCase):
    def test_active_tender_becomes_a_measured_public_demand_observation(self):
        data = observations(facts(), boamp([{"id": "1", "title": "Prestation de service test", "url": "https://boamp.test/1", "notice_kind": "TENDER", "response_deadline": "2026-09-30T12:00:00+00:00"}]))
        self.assertEqual(data["collection_status"], "COMPLETED")
        result = enrich(data, datetime(2026, 9, 2, tzinfo=UTC))
        validate(data, result)
        self.assertEqual(result["status"], "COMPLETED")

    def test_expired_tender_is_not_current_demand(self):
        data = observations(facts(), boamp([{"id": "1", "title": "Prestation de service test", "url": "https://boamp.test/1", "notice_kind": "TENDER", "response_deadline": "2026-08-30T12:00:00+00:00"}]))
        self.assertEqual(data["collection_status"], "COMPLETED")
        result = enrich(data, datetime(2026, 9, 2, tzinfo=UTC))
        validate(data, result)
        self.assertEqual(result["status"], "NO_EVIDENCE")

    def test_boamp_failure_is_never_negative_demand_evidence(self):
        data = observations(facts(), boamp([], "UNRESOLVED"))
        result = enrich(data, datetime(2026, 9, 2, tzinfo=UTC))
        validate(data, result)
        self.assertEqual(result["status"], "UNRESOLVED")

    def test_two_buyers_raise_high_institutional_demand(self):
        data = observations(facts(), boamp([
            {"id": "1", "title": "Prestation de service test", "buyer": "Ville A", "url": "https://boamp.test/1", "notice_kind": "TENDER", "response_deadline": "2026-09-30T12:00:00+00:00"},
            {"id": "2", "title": "Autre prestation de service test", "buyer": "Ville B", "url": "https://boamp.test/2", "notice_kind": "TENDER", "response_deadline": "2026-09-30T12:00:00+00:00"},
        ]))
        self.assertEqual(data["indicators"]["institutional"]["status"], "HIGH_INSTITUTIONAL_DEMAND")
        self.assertEqual(data["indicators"]["trends"]["status"], "DISABLED")

    def test_gate_hold_records_skipped_not_no_evidence(self):
        gate = {"operator_access": {"allow_external_collection": False, "reasons": ["Hors profil."]}}
        data = build_blocked(facts(), gate, datetime(2026, 9, 2, tzinfo=UTC))
        self.assertEqual(data["collection_status"], "SKIPPED_BY_OPERATOR_GATE")
        self.assertEqual(data["indicators"]["institutional"]["status"], "SKIPPED_BY_OPERATOR_GATE")
