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
RESEARCH_POLICY = {
    "schema": "lawradar-research-candidate-policy-v1",
    "maximum_signals_per_run": 3,
    "minimum_score": 4,
    "eligible_legal_statuses": ["PUBLISHED", "IN_FORCE", "CONSULTATION_OPEN", "DRAFT"],
    "business_indicators": ["obligation", "cee", "assainissement", "station d'epuration", "mise en service"],
    "routine_exclusions": ["nomination", "recrutement", "taux de cotisation", "service de radio"],
}
NOW = datetime(2026, 9, 2, tzinfo=UTC)


class PilotReadinessTests(unittest.TestCase):
    def test_legacy_signal_without_facts_waits_for_next_delivery(self):
        entry = build(dossier([signal()]), POLICY, PROFILE, NOW, RESEARCH_POLICY)["signals"][0]
        self.assertEqual(entry["status"], "WAITING_FOR_OPPORTUNITY_FACTS")
        self.assertFalse(entry["ready_for_pilots"])

    def test_accessible_retained_signal_is_ready(self):
        entry = build(dossier([signal(attached_facts=facts())]), POLICY, PROFILE, NOW, RESEARCH_POLICY)["signals"][0]
        self.assertEqual(entry["status"], "READY_FOR_PILOTS")
        self.assertTrue(entry["ready_for_pilots"])

    def test_regulated_signal_is_held_before_external_collection(self):
        protected = facts()
        protected["operator_access"] = {"sector": "MEDICINES", "direct_offer_status": "OUT_OF_PROFILE", "peripheral_role_evidence": "MISSING", "evidence_status": "PARTIAL"}
        entry = build(dossier([signal(attached_facts=protected)]), POLICY, PROFILE, NOW, RESEARCH_POLICY)["signals"][0]
        self.assertEqual(entry["status"], "HOLD_BY_OPERATOR_ACCESS")
        self.assertFalse(entry["ready_for_pilots"])

    def test_infeasible_signal_is_not_sent_to_pilots(self):
        infeasible = facts()
        infeasible["requirements"]["minimum_startup_capital_eur"] = 5000
        entry = build(dossier([signal(attached_facts=infeasible)]), POLICY, PROFILE, NOW, RESEARCH_POLICY)["signals"][0]
        self.assertEqual(entry["status"], "DISCARDED_BY_FILTERS")
        self.assertFalse(entry["ready_for_pilots"])

    def test_energy_cee_signal_can_reach_research_agents_while_business_facts_are_open(self):
        energy = facts()
        energy["operator_access"] = {
            "sector": "ENERGY_EFFICIENCY",
            "direct_offer_status": "ACCESSIBLE",
            "peripheral_role_evidence": "NOT_APPLICABLE",
            "evidence_status": "PARTIAL",
        }
        energy["requirements"] = {
            **energy["requirements"],
            "minimum_startup_capital_eur": None,
            "estimated_time_to_market_weeks": None,
            "evidence_status": "MISSING",
        }
        entry = build(dossier([signal(attached_facts=energy)]), POLICY, PROFILE, NOW, RESEARCH_POLICY)["signals"][0]
        self.assertEqual(entry["status"], "READY_FOR_PILOTS")
        self.assertTrue(entry["ready_for_pilots"])

    def test_discarded_signal_with_economic_indicator_gets_research_only_route(self):
        candidate = facts()
        candidate["title"] = "Projet de station d'épuration : autorisation et exploitation"
        candidate["legal"]["text_status"] = "CONSULTATION_OPEN"
        candidate["legal"]["proof_status"] = "PARTIAL"
        item = signal(attached_facts=candidate)
        item["radar"]["status"] = "DISCARDED"
        entry = build(dossier([item]), POLICY, PROFILE, NOW, RESEARCH_POLICY)["signals"][0]
        self.assertEqual(entry["status"], "RESEARCH_CANDIDATE")
        self.assertTrue(entry["ready_for_pilots"])
        self.assertEqual(entry["client_scope"], "RESEARCH_ONLY")
        self.assertFalse(entry["entrepreneur_allowed"])

    def test_discarded_routine_signal_is_not_sent_to_external_agents(self):
        routine = facts()
        routine["title"] = "Arrêté de recrutement et de nomination"
        item = signal(attached_facts=routine)
        item["radar"]["status"] = "DISCARDED"
        entry = build(dossier([item]), POLICY, PROFILE, NOW, RESEARCH_POLICY)["signals"][0]
        self.assertEqual(entry["status"], "NOT_RETAINED")
        self.assertFalse(entry["ready_for_pilots"])

    def test_research_route_is_hard_capped_per_delivery(self):
        items = []
        for suffix in range(4):
            candidate = facts(f"signal:{suffix}")
            candidate["title"] = f"Obligation CEE {suffix} pour la mise en service"
            candidate["legal"]["text_status"] = "CONSULTATION_OPEN"
            candidate["legal"]["proof_status"] = "PARTIAL"
            item = signal(f"signal:{suffix}", candidate)
            item["radar"]["status"] = "DISCARDED"
            items.append(item)
        result = build(dossier(items), POLICY, PROFILE, NOW, RESEARCH_POLICY)
        self.assertEqual(result["summary"]["research_candidates_selected"], 3)
        self.assertEqual(result["summary"]["counts_by_status"]["RESEARCH_CANDIDATE_DEFERRED"], 1)

    def test_same_consultation_page_is_researched_once(self):
        items = []
        for suffix in ("first", "second"):
            candidate = facts(f"signal:{suffix}")
            candidate["title"] = f"Obligation CEE {suffix} de mise en service"
            candidate["legal"]["text_status"] = "CONSULTATION_OPEN"
            candidate["legal"]["proof_status"] = "PARTIAL"
            item = signal(f"signal:{suffix}", candidate)
            item["source"]["source_id"] = f"consultdd:https://example.test/projet-a1234.html"
            item["radar"]["status"] = "DISCARDED"
            items.append(item)
        result = build(dossier(items), POLICY, PROFILE, NOW, RESEARCH_POLICY)
        self.assertEqual(result["summary"]["research_candidates_selected"], 1)
        self.assertEqual(result["summary"]["counts_by_status"]["RESEARCH_CANDIDATE_DEFERRED"], 1)
