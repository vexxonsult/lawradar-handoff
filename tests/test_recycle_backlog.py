import copy
import unittest
from datetime import UTC, datetime

from scripts.utils.recycle_backlog import capture, empty_backlog, recycle


NOW = datetime(2026, 9, 2, tzinfo=UTC)


def facts():
    return {
        "schema": "lawradar-opportunity-facts-v1",
        "signal_id": "signal:recycle-1",
        "title": "Obligation test",
        "keywords": ["obligation test"],
        "affected_scope": ["entreprises françaises"],
        "legal": {
            "jurisdiction": "FR",
            "text_status": "IN_FORCE",
            "proof_status": "VERIFIED",
            "effective_date": "2026-09-10",
            "affected_scope": ["entreprises françaises"],
        },
        "requirements": {
            "required_capabilities": ["analyse_ia"],
            "required_authorizations": [],
            "dependencies": [],
            "minimum_startup_capital_eur": 500,
            "estimated_time_to_market_weeks": 4,
            "evidence_status": "VERIFIED",
        },
    }


def policy():
    return {
        "schema": "lawradar-compliance-policy-v1",
        "accepted_jurisdictions": ["FR"],
        "actionable_text_statuses": ["PUBLISHED", "IN_FORCE"],
        "watch_text_statuses": ["CONSULTATION_OPEN", "DRAFT"],
        "maximum_effective_delay_days": 183,
    }


def profile(capital):
    return {
        "schema": "lawradar-operator-profile-v1",
        "available_capabilities": ["analyse_ia"],
        "available_authorizations": [],
        "max_startup_capital_eur": capital,
        "max_time_to_market_weeks": 8,
        "accepted_geographies": ["FR"],
        "allowed_dependency_risk": "LOW",
    }


def dossier():
    return {
        "schema": "lawradar-universal-signal-v2",
        "signals": [{
            "id": "signal:recycle-1",
            "source": {"source_id": "jorf:1", "evidence": {"url": "https://official.test/1"}},
            "radar": {"status": "RETAINED", "reason": "Test"},
            "opportunity_facts": facts(),
            "enrichments": {
                "press": {"status": "PENDING", "result": None},
                "demand": {"status": "PENDING", "result": None},
                "market": {"status": "PENDING", "result": None},
            },
        }],
    }


class RecycleBacklogTests(unittest.TestCase):
    def test_captures_blocked_signal_with_immutable_facts(self):
        backlog = capture(
            dossier(), empty_backlog(), policy(), profile(100),
            queue={"processed": [{"fingerprint": "a", "source_id": "jorf:empty", "deterministic_status": "UNRESOLVED", "reason": "PRIMARY_TEXT_EMPTY"}]},
            now=NOW,
        )
        self.assertEqual(len(backlog["records"]), 1)
        self.assertEqual(backlog["records"][0]["latest_status"], "DISCARD")
        self.assertEqual(backlog["queue_audit"]["unrecoverable_queue_entries"][0]["source_id"], "jorf:empty")

    def test_updated_profile_reopens_only_after_true_filter_pass(self):
        backlog = capture(dossier(), empty_backlog(), policy(), profile(100), now=NOW)
        next_backlog, ready = recycle(backlog, policy(), profile(1000), now=NOW)
        self.assertEqual(next_backlog["records"][0]["state"], "REOPENED")
        self.assertEqual(ready["reopened_count"], 1)
        reopened = ready["reopened"][0]["signal"]
        self.assertEqual(reopened["deterministic_filters"]["final_constraint"], "PASS")
        self.assertTrue(reopened["deterministic_filters"]["operator_access"]["allow_external_collection"])

    def test_unchanged_profile_does_not_repeat_a_deterministic_evaluation(self):
        backlog = capture(dossier(), empty_backlog(), policy(), profile(100), now=NOW)
        before = copy.deepcopy(backlog)
        next_backlog, ready = recycle(backlog, policy(), profile(100), now=NOW)
        self.assertEqual(next_backlog, before)
        self.assertEqual(ready["reopened_count"], 0)

