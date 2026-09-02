import copy
import unittest

from scripts.validate_demand_enrichment import validate


def observations(items=None, status="COMPLETED", errors=None):
    return {
        "schema": "lawradar-demand-observations-v2",
        "signal_id": "signal:1",
        "signal_hash": "hash",
        "collected_at_utc": "2026-09-02T12:00:00Z",
        "collection_status": status,
        "indicators": {
            "trends": {"status": "DISABLED", "experimental_manual_only": True, "ratio_7d_vs_prior_83d": None, "surge_detected": None},
            "autocomplete": {"status": "DISABLED", "experimental_manual_only": True, "intent_terms_found": [], "commercial_intent": None},
            "institutional": {"status": "NONE", "open_tender_count": 0, "pre_information_count": 0, "distinct_buyer_count": 0},
        },
        "observations": items if items is not None else [{"url": "https://trend.test/query", "title": "Indice de recherche", "provider": "Exemple", "metric": "interest", "value": 42, "unit": "index", "period": "2026-08", "geography": "FR", "retrieved_at_utc": "2026-09-02T12:00:00Z"}],
        "errors": errors or [],
    }


def enrichment(status="COMPLETED"):
    return {
        "schema": "lawradar-agent-enrichment-v1",
        "agent": "demand",
        "signal_id": "signal:1",
        "status": status,
        "observed_at_utc": "2026-09-02T12:01:00Z",
        "summary": "Un intérêt de recherche a été mesuré. [1]",
        "sources": [{"url": "https://trend.test/query", "title": "Indice de recherche"}],
        "limitations": ["Indice relatif, pas un volume de recherche."],
        "details": {
            "signal_hash": "hash",
            "collection_status": "COMPLETED",
            "observations_total": 1,
            "conclusions": [{"url": "https://trend.test/query", "interpretation": "SEARCH_INTEREST", "why": "La métrique mesure un intérêt relatif."}],
            "indicators": observations()["indicators"],
        },
        "score": None,
    }


class ValidateDemandEnrichmentTests(unittest.TestCase):
    def test_accepts_a_measured_and_cited_observation(self):
        validate(observations(), enrichment())

    def test_rejects_an_invented_observation_url(self):
        invalid = enrichment()
        invalid["sources"][0]["url"] = "https://invented.test/query"
        with self.assertRaises(ValueError):
            validate(observations(), invalid)

    def test_rejects_no_evidence_when_measurements_exist(self):
        invalid = enrichment("NO_EVIDENCE")
        invalid["sources"] = []
        invalid["details"]["conclusions"] = [{"url": "https://trend.test/query", "interpretation": "NOT_RELEVANT", "why": "Autre sujet."}]
        with self.assertRaises(ValueError):
            validate(observations(), invalid)

    def test_accepts_empty_completed_collection_as_no_evidence(self):
        empty = observations(items=[])
        result = enrichment("NO_EVIDENCE")
        result["summary"] = "Aucune observation de demande n'a été fournie par la collecte exécutée."
        result["sources"] = []
        result["details"]["observations_total"] = 0
        result["details"]["conclusions"] = []
        validate(empty, result)

    def test_rejects_completed_without_citation(self):
        invalid = copy.deepcopy(enrichment())
        invalid["summary"] = "Un intérêt de recherche a été mesuré."
        with self.assertRaises(ValueError):
            validate(observations(), invalid)

    def test_rejects_an_observation_without_a_measured_period(self):
        value = observations()
        del value["observations"][0]["period"]
        with self.assertRaises(ValueError):
            validate(value, enrichment())
