import tempfile
import unittest
from pathlib import Path

from scripts.consolidate_client_artifacts import consolidate, discover


def enrichment(agent: str) -> dict:
    return {
        "schema": "lawradar-agent-enrichment-v1",
        "agent": agent,
        "signal_id": "signal:1",
        "status": "COMPLETED" if agent == "demand" else "NO_EVIDENCE",
        "observed_at_utc": "2026-09-03T06:00:00+00:00",
        "summary": "Résultat traçable.",
        "sources": [],
        "limitations": [],
        "details": {},
        "score": None,
    }


def core() -> dict:
    return {
        "schema": "lawradar-universal-signal-v2",
        "signals": [{
            "id": "signal:1",
            "radar": {"status": "RETAINED"},
            "enrichments": {
                "press": {"status": "PENDING", "result": None},
                "demand": {"status": "PENDING", "result": None},
                "market": {"status": "PENDING", "result": None},
            },
        }],
    }


def readiness() -> dict:
    return {
        "schema": "lawradar-agent-pilot-readiness-v1",
        "signals": [{
            "signal_id": "signal:1",
            "ready_for_pilots": True,
            "filters": {"final_constraint": "PASS", "operator_access": {"status": "PASS"}},
        }],
    }


class ConsolidateClientArtifactsTests(unittest.TestCase):
    def test_attaches_filters_and_three_independent_enrichments(self):
        result = consolidate(core(), [enrichment(agent) for agent in ("press", "demand", "market")], readiness())
        signal = result["signals"][0]
        self.assertEqual(signal["deterministic_filters"]["final_constraint"], "PASS")
        self.assertEqual(signal["enrichments"]["demand"]["status"], "COMPLETED")
        self.assertTrue(result["client_context"]["core_immutable"])

    def test_rejects_an_incomplete_parallel_fanout(self):
        with self.assertRaisesRegex(ValueError, "market"):
            consolidate(core(), [enrichment("press"), enrichment("demand")], readiness())

    def test_discovery_rejects_duplicate_agent_signal_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import json
            for folder in ("a", "b"):
                path = root / folder
                path.mkdir()
                (path / "press-enrichment.json").write_text(json.dumps(enrichment("press")), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dupliquée"):
                discover(root)


if __name__ == "__main__":
    unittest.main()
