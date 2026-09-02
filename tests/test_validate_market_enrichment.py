import copy
import unittest

from scripts.validate_market_enrichment import validate


def observations(items=None, status="COMPLETED", errors=None):
    return {
        "schema": "lawradar-market-observations-v1",
        "signal_id": "signal:1",
        "signal_hash": "hash",
        "collected_at_utc": "2026-09-02T12:00:00Z",
        "collection_status": status,
        "observations": items if items is not None else [{"url": "https://provider.test/offer", "title": "Offre observée", "provider": "Exemple", "actor": "Acteur Exemple", "observation_type": "OFFER", "geography": "FR", "retrieved_at_utc": "2026-09-02T12:00:00Z", "excerpt": "Une offre documentée pour le périmètre étudié."}],
        "errors": errors or [],
    }


def enrichment(status="COMPLETED"):
    return {
        "schema": "lawradar-agent-enrichment-v1",
        "agent": "market",
        "signal_id": "signal:1",
        "status": status,
        "observed_at_utc": "2026-09-02T12:01:00Z",
        "summary": "Une offre est documentée dans le périmètre étudié. [1]",
        "sources": [{"url": "https://provider.test/offer", "title": "Offre observée"}],
        "limitations": ["Cette observation ne mesure pas la taille totale du marché."],
        "details": {"signal_hash": "hash", "collection_status": "COMPLETED", "observations_total": 1, "conclusions": [{"url": "https://provider.test/offer", "interpretation": "OFFER", "why": "La source décrit une offre."}]},
        "score": None,
    }


class ValidateMarketEnrichmentTests(unittest.TestCase):
    def test_accepts_a_cited_market_observation(self):
        validate(observations(), enrichment())

    def test_rejects_a_source_outside_the_observations(self):
        invalid = enrichment()
        invalid["sources"][0]["url"] = "https://invented.test/offer"
        with self.assertRaises(ValueError):
            validate(observations(), invalid)

    def test_rejects_a_long_copied_excerpt(self):
        value = observations()
        value["observations"][0]["excerpt"] = "mot " * 26
        with self.assertRaises(ValueError):
            validate(value, enrichment())

    def test_accepts_empty_collection_as_no_evidence(self):
        empty = observations(items=[])
        result = enrichment("NO_EVIDENCE")
        result["summary"] = "Aucune observation de marché n'a été fournie par la collecte exécutée."
        result["sources"] = []
        result["details"]["observations_total"] = 0
        result["details"]["conclusions"] = []
        validate(empty, result)

    def test_rejects_completed_without_citation(self):
        invalid = copy.deepcopy(enrichment())
        invalid["summary"] = "Une offre est documentée dans le périmètre étudié."
        with self.assertRaises(ValueError):
            validate(observations(), invalid)
