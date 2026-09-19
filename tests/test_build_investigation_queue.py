import unittest
from datetime import UTC, datetime, timedelta

from scripts.build_investigation_queue import build


NOW = datetime(2026, 9, 13, 12, tzinfo=UTC)


def enrichment(agent, status, limitations):
    return {
        "status": status,
        "result": {
            "schema": "lawradar-agent-enrichment-v1",
            "agent": agent,
            "signal_id": "signal:energy",
            "status": status,
            "observed_at_utc": NOW.isoformat(),
            "summary": "Test.",
            "sources": [],
            "limitations": limitations,
            "details": {},
            "score": None,
        },
    }


def context():
    return {
        "schema": "lawradar-universal-signal-v2",
        "run": {"id": "run:1"},
        "signals": [{
            "id": "signal:energy",
            "source": {"source_id": "jorf:1", "evidence": {"official": {"title": "Décret énergie"}}},
            "radar": {"status": "RETAINED"},
            "opportunity_facts": {
                "title": "Décret énergie",
                "requirements": {
                    "required_authorizations": ["agrément"],
                    "dependencies": [],
                    "minimum_startup_capital_eur": None,
                    "estimated_time_to_market_weeks": None,
                },
            },
            "deterministic_filters": {
                "final_constraint": "INVESTIGATE",
                "feasibility": {"reasons": ["Capital de départ inconnu."]},
            },
            "enrichments": {
                "press": enrichment("press", "UNRESOLVED", ["Réponse Claude non exploitable.", "HTTP 429 rate-limit temporaire"]),
                "market": enrichment("market", "UNRESOLVED", ["Réponse Claude non exploitable."]),
                "demand": enrichment("demand", "COMPLETED", []),
            },
        }],
    }


def readiness():
    return {
        "schema": "lawradar-agent-pilot-readiness-v1",
        "signals": [{
            "signal_id": "signal:energy",
            "status": "READY_FOR_PILOTS",
            "filters": {"final_constraint": "INVESTIGATE"},
        }],
    }


class InvestigationQueueTests(unittest.TestCase):
    def test_turns_technical_enrichment_failures_into_one_bounded_retry(self):
        result = build(context(), readiness(), now=NOW)
        item = result["items"][0]
        self.assertEqual(item["status"], "WAITING_FOR_EVIDENCE")
        self.assertEqual(item["automatic_attempts"], 1)
        self.assertEqual(item["next_retry_not_before_utc"], (NOW + timedelta(hours=6)).isoformat())
        self.assertEqual({question["id"] for question in item["questions"]}, {"OPERATIONAL_FEASIBILITY", "PRESS_QUALIFICATION", "MARKET_RELEVANCE"})
        self.assertTrue(next(question for question in item["questions"] if question["id"] == "PRESS_QUALIFICATION")["automatic_retry"])
        self.assertFalse(next(question for question in item["questions"] if question["id"] == "OPERATIONAL_FEASIBILITY")["automatic_retry"])

    def test_second_technical_attempt_requires_review_instead_of_looping(self):
        previous = build(context(), readiness(), now=NOW)
        result = build(context(), readiness(), previous, now=NOW + timedelta(hours=6))
        item = result["items"][0]
        self.assertEqual(item["automatic_attempts"], 2)
        self.assertEqual(item["status"], "REVIEW_REQUIRED")
        self.assertIsNone(item["next_retry_not_before_utc"])

    def test_contract_repair_grants_one_clean_technical_retry(self):
        previous = build(context(), readiness(), now=NOW)
        previous["items"][0]["qualification_contract_version"] = "tool-envelope-v1"
        result = build(context(), readiness(), previous, now=NOW + timedelta(hours=6))
        item = result["items"][0]
        self.assertEqual(item["automatic_attempts"], 1)
        self.assertEqual(item["status"], "WAITING_FOR_EVIDENCE")

    def test_non_retained_signal_never_enters_the_queue(self):
        value = context()
        value["signals"][0]["radar"]["status"] = "DISCARDED"
        self.assertEqual(build(value, readiness(), now=NOW)["items"], [])
