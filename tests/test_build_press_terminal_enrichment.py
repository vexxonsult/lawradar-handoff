import unittest

from scripts.build_press_terminal_enrichment import build


def candidates(items=None, errors=None):
    return {
        "schema": "lawradar-press-candidates-v1",
        "signal_id": "signal:1",
        "signal_hash": "hash",
        "window": {"from": "2026-08-19", "to": "2026-09-02"},
        "queries": [],
        "candidates_total": len(items or []),
        "candidates_after_dedup": len(items or []),
        "candidates": items or [],
        "errors": errors or [],
    }


class BuildPressTerminalEnrichmentTests(unittest.TestCase):
    def test_no_evidence_requires_a_successful_empty_collection(self):
        result = build(candidates(), "2026-09-02T12:00:00Z")
        self.assertEqual(result["status"], "NO_EVIDENCE")
        self.assertEqual(result["sources"], [])

    def test_source_failure_becomes_unresolved(self):
        result = build(candidates(errors=[{"source": "gdelt", "error": "timeout"}]), "2026-09-02T12:00:00Z")
        self.assertEqual(result["status"], "UNRESOLVED")

    def test_optional_source_failure_can_still_be_no_evidence(self):
        value = candidates(errors=[{"source": "gdelt", "error": "timeout"}])
        value["collection_successful"] = True
        result = build(value, "2026-09-02T12:00:00Z")
        self.assertEqual(result["status"], "NO_EVIDENCE")

    def test_candidates_require_qualification(self):
        with self.assertRaises(ValueError):
            build(candidates(items=[{"url": "https://journal.test"}]))
