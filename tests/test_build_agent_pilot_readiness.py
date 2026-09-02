import unittest
from datetime import UTC, datetime

from scripts.build_agent_pilot_readiness import build


def facts(signal_id="signal:test"):
    return {
        "schema": "lawradar-opportunity-facts-v1", "signal_id": signal_id,
        "title": "Obligation test", "keywords": ["obligation", "test"], "affected_scope": ["entreprises françaises"],
        "legal": {"jurisdiction": "FR", "text_status": "IN_FORCE", "proof_status": "VERIFIED", "effective_date": "2026-09-10", "affected_scope": ["entreprises françaises"]},
        "requirements": {"required_capabilities": ["analyse_ia"], "required_authorizations": [], "dependencies": [], "minimum_startup_capital_eur": 500, "estimated_time_to_market_weeks": 4, "evidence_status": "VERIFIED"},
    }


def dossier(items):
    return {"schema": "lawradar-universal-signal-v1", "run": {"id": "run:1"}, "signals": items}


def signal(signal_id="signal:test", attached_facts=None):
    item = {"id": signal_id, "source": {"source_id": "jorf:1"}, "radar": {"status": "RETAINED"}}
    if attached_facts is not None:
        item["opportunity_facts"] = attached_facts
    return item


POLICY = {"schema": "lawradar-compliance-policy-v1", "accepted_jurisdictions": ["FR"], "actionable_text_statuses": ["PUBLISHED", "IN_FORCE"], "watch_text_statuses": ["CONSULTATION_OPEN", "DRAFT"], "maximum_effective_delay_days": 183}
PROFILE = {"schema": "lawradar-operator-profile-v1", "available_capabilities": ["analyse_ia"], "available_authorizations": [], "max_startup_capital_eur": 2000, "max_time_to_market_weeks": 8, "accepted_geographies": ["FR"], "allowed_dependency_risk": "LOW"}
NOW = datetime(2026, 9, 2, tzinfo=UTC)


class PilotReadinessTests(unittest.TestCase):
    def test_legacy_signal_without_facts_waits_for_next_delivery(self):
        entry = build(dossier([signal()]), POLICY, PROFILE, NOW)["signals"][0]
        self.assertEqual(entry["status"], "WAITING_FOR_OPPORTUNITY_FACTS")
        self.assertFalse(entry["ready_for_pilots"])

    def test_accessible_retained_signal_is_ready(self):
        entry = build(dossier([signal(attached_facts=facts())]), POLICY, PROFILE, NOW)["signals"][0]
        self.assertEqual(entry["status"], "READY_FOR_PILOTS")
        self.assertTrue(entry["ready_for_pilots"])

    def test_regulated_signal_is_held_before_external_collection(self):
        protected = facts()
        protected["operator_access"] = {"sector": "MEDICINES", "direct_offer_status": "OUT_OF_PROFILE", "peripheral_role_evidence": "MISSING", "evidence_status": "PARTIAL"}
        entry = build(dossier([signal(attached_facts=protected)]), POLICY, PROFILE, NOW)["signals"][0]
        self.assertEqual(entry["status"], "HOLD_BY_OPERATOR_ACCESS")
        self.assertFalse(entry["ready_for_pilots"])

    def test_infeasible_signal_is_not_sent_to_pilots(self):
        infeasible = facts()
        infeasible["requirements"]["minimum_startup_capital_eur"] = 5000
        entry = build(dossier([signal(attached_facts=infeasible)]), POLICY, PROFILE, NOW)["signals"][0]
        self.assertEqual(entry["status"], "DISCARDED_BY_FILTERS")
        self.assertFalse(entry["ready_for_pilots"])
