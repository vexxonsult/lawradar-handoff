import copy
import unittest

from scripts.validate_press_enrichment import validate


def candidates(errors=None):
    return {
        "schema": "lawradar-press-candidates-v1",
        "signal_id": "signal:1",
        "signal_hash": "hash",
        "observed_at_utc": "2026-09-02T12:00:00Z",
        "window": {"from": "2026-08-19", "to": "2026-09-02"},
        "queries": [],
        "candidates_total": 1,
        "candidates_after_dedup": 1,
        "candidates": [{"url": "https://journal.test/article", "title": "Le décret concerné", "excerpt": None}],
        "errors": errors or [],
    }


def enrichment(status="COMPLETED"):
    return {
        "schema": "lawradar-agent-enrichment-v1",
        "agent": "press",
        "signal_id": "signal:1",
        "status": status,
        "observed_at_utc": "2026-09-02T12:01:00Z",
        "summary": "L'article cite le décret concerné. [1]",
        "sources": [{"url": "https://journal.test/article", "title": "Le décret concerné"}],
        "limitations": [],
        "details": {
            "signal_hash": "hash",
            "window": {"from": "2026-08-19", "to": "2026-09-02"},
            "queries": [],
            "candidates_total": 1,
            "candidates_after_dedup": 1,
            "coverage_level": "LOW",
            "decisions": [{"url": "https://journal.test/article", "relevance": "DIRECT", "why_linked": "Le titre cite le décret."}],
        },
        "score": None,
    }


class ValidatePressEnrichmentTests(unittest.TestCase):
    def test_accepts_a_cited_source_from_the_candidates(self):
        validate(candidates(), enrichment())

    def test_rejects_a_hallucinated_url(self):
        invalid = enrichment()
        invalid["sources"][0]["url"] = "https://invented.test/article"
        with self.assertRaises(ValueError):
            validate(candidates(), invalid)

    def test_rejects_no_evidence_when_collection_failed(self):
        no_evidence = enrichment("NO_EVIDENCE")
        no_evidence["sources"] = []
        no_evidence["details"]["decisions"] = [{"url": "https://journal.test/article", "relevance": "NOT_LINKED", "why_linked": "Autre texte."}]
        no_evidence["details"]["coverage_level"] = "NONE"
        with self.assertRaises(ValueError):
            validate(candidates(errors=[{"source": "gdelt", "error": "timeout"}]), no_evidence)

    def test_allows_no_evidence_when_only_an_optional_source_failed(self):
        no_evidence = enrichment("NO_EVIDENCE")
        no_evidence["sources"] = []
        no_evidence["details"]["decisions"] = [{"url": "https://journal.test/article", "relevance": "NOT_LINKED", "why_linked": "Autre texte."}]
        no_evidence["details"]["coverage_level"] = "NONE"
        value = candidates(errors=[{"source": "gdelt", "error": "timeout"}])
        value["collection_successful"] = True
        validate(value, no_evidence)

    def test_rejects_completed_without_a_citation(self):
        invalid = copy.deepcopy(enrichment())
        invalid["summary"] = "L'article cite le décret concerné."
        with self.assertRaises(ValueError):
            validate(candidates(), invalid)
