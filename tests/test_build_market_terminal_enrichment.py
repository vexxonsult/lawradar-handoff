import unittest

from scripts.build_market_terminal_enrichment import build


def observations(status="NO_EVIDENCE", errors=None):
    return {
        "schema": "lawradar-market-observations-v1", "signal_id": "signal:1", "signal_hash": "hash",
        "collected_at_utc": "2026-09-02T12:00:00Z", "collection_status": status,
        "observations": [], "errors": errors or [],
    }


class BuildMarketTerminalEnrichmentTests(unittest.TestCase):
    def test_empty_completed_collection_becomes_no_evidence(self):
        self.assertEqual(build(observations())["status"], "NO_EVIDENCE")

    def test_unresolved_collection_stays_unresolved(self):
        self.assertEqual(build(observations("UNRESOLVED", [{"error": "timeout"}]))["status"], "UNRESOLVED")
