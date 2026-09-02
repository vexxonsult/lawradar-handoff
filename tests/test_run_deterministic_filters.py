import copy
import unittest
from datetime import UTC, datetime

from scripts.run_deterministic_filters import evaluate


def facts():
    return {
        "schema": "lawradar-opportunity-facts-v1", "signal_id": "signal:1",
        "title": "Obligation test", "keywords": ["obligation test"], "affected_scope": ["entreprises françaises"],
        "legal": {"jurisdiction": "FR", "text_status": "IN_FORCE", "proof_status": "VERIFIED", "effective_date": "2026-09-10", "affected_scope": ["entreprises françaises"]},
        "requirements": {"required_capabilities": ["analyse_ia"], "required_authorizations": [], "dependencies": [], "minimum_startup_capital_eur": 500, "estimated_time_to_market_weeks": 4, "evidence_status": "VERIFIED"},
    }


def policy():
    return {"schema": "lawradar-compliance-policy-v1", "accepted_jurisdictions": ["FR"], "actionable_text_statuses": ["PUBLISHED", "IN_FORCE"], "watch_text_statuses": ["CONSULTATION_OPEN", "DRAFT"], "maximum_effective_delay_days": 183}


def profile():
    return {"schema": "lawradar-operator-profile-v1", "available_capabilities": ["analyse_ia"], "available_authorizations": [], "max_startup_capital_eur": 2000, "max_time_to_market_weeks": 8, "accepted_geographies": ["FR"], "allowed_dependency_risk": "LOW"}


class DeterministicFilterTests(unittest.TestCase):
    def evaluate(self, data):
        return evaluate(data, policy(), profile(), datetime(2026, 9, 2, tzinfo=UTC))

    def test_passes_verified_and_feasible_facts(self):
        output = self.evaluate(facts())
        self.assertEqual(output["compliance"]["status"], "PASS")
        self.assertEqual(output["feasibility"]["status"], "PASS")
        self.assertEqual(output["final_constraint"], "PASS")

    def test_missing_legal_proof_requires_investigation(self):
        data = facts()
        data["legal"]["proof_status"] = "MISSING"
        output = self.evaluate(data)
        self.assertEqual(output["compliance"]["status"], "INVESTIGATE")
        self.assertEqual(output["final_constraint"], "INVESTIGATE")

    def test_expired_text_is_discarded(self):
        data = facts()
        data["legal"]["text_status"] = "EXPIRED"
        self.assertEqual(self.evaluate(data)["final_constraint"], "DISCARD")

    def test_future_draft_is_watch_not_discard(self):
        data = facts()
        data["legal"]["text_status"] = "DRAFT"
        self.assertEqual(self.evaluate(data)["compliance"]["status"], "WATCH")

    def test_resource_capital_over_profile_is_discard(self):
        data = facts()
        data["requirements"]["minimum_startup_capital_eur"] = 2500
        self.assertEqual(self.evaluate(data)["feasibility"]["status"], "DISCARD")

    def test_unknown_requirements_require_investigation_not_discard(self):
        data = facts()
        data["requirements"]["minimum_startup_capital_eur"] = None
        data["requirements"]["estimated_time_to_market_weeks"] = None
        data["requirements"]["evidence_status"] = "MISSING"
        self.assertEqual(self.evaluate(data)["feasibility"]["status"], "INVESTIGATE")

    def test_missing_required_capability_is_discard_for_current_profile(self):
        data = copy.deepcopy(facts())
        data["requirements"]["required_capabilities"] = ["installation_certifiee"]
        self.assertEqual(self.evaluate(data)["feasibility"]["status"], "DISCARD")

    def test_regulated_direct_offer_without_peripheral_role_is_held_before_enrichment(self):
        data = facts()
        data["operator_access"] = {
            "sector": "MEDICINES",
            "direct_offer_status": "OUT_OF_PROFILE",
            "peripheral_role_evidence": "MISSING",
            "evidence_status": "PARTIAL",
        }
        output = self.evaluate(data)
        self.assertEqual(output["operator_access"]["status"], "HOLD")
        self.assertEqual(output["operator_access"]["route"], "LEGAL_ROLE_CHECK_ONLY")
        self.assertFalse(output["operator_access"]["allow_external_collection"])
        self.assertEqual(output["final_constraint"], "INVESTIGATE")

    def test_verified_peripheral_role_can_continue_to_full_enrichment(self):
        data = facts()
        data["operator_access"] = {
            "sector": "MEDICINES",
            "direct_offer_status": "OUT_OF_PROFILE",
            "peripheral_role_evidence": "VERIFIED",
            "evidence_status": "VERIFIED",
        }
        output = self.evaluate(data)
        self.assertEqual(output["operator_access"]["status"], "PASS")
        self.assertTrue(output["operator_access"]["allow_external_collection"])
