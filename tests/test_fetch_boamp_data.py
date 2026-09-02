import unittest
from datetime import UTC, datetime

from scripts.fetch_boamp_data import collect


def facts():
    return {
        "schema": "lawradar-opportunity-facts-v1",
        "signal_id": "signal:water-filter",
        "keywords": ["filtre à eau écologique", "traitement eau"],
        "affected_scope": ["installation de filtres à eau pour entreprises"],
        "legal": {},
        "requirements": {},
    }


def config():
    return {
        "schema": "lawradar-boamp-collector-config-v1",
        "activation": "manual_only",
        "endpoint": "https://example.test/boamp",
        "dataset": "boamp",
        "search_field": "objet",
        "limits": {
            "max_queries_per_signal": 2,
            "page_size": 2,
            "max_pages_per_query": 2,
            "max_records_in_output": 10,
            "minimum_interval_seconds": 0,
            "attempts_per_request": 1,
            "timeout_seconds": 2,
        },
    }


class FetchBoampDataTests(unittest.TestCase):
    def test_collects_compact_current_market_observations_with_pagination(self):
        calls = []

        def fetch(endpoint, params, timeout):
            calls.append((endpoint, params, timeout))
            self.assertNotIn("Cibelco", params["where"])
            offset = params["offset"]
            if offset == 0:
                return {"total_count": 3, "results": [
                    {"idweb": "a", "objet": "Installation de filtres à eau", "dateparution": "2026-09-01", "datelimitereponse": "2026-09-10T12:00:00+00:00", "nomacheteur": "Ville A", "nature": "APPEL_OFFRE", "nature_libelle": "Avis de marché", "etat": "INITIAL", "url_avis": "https://boamp.test/a"},
                    {"idweb": "b", "objet": "Traitement de l'eau", "dateparution": "2026-09-01", "datelimitereponse": None, "nomacheteur": "Ville A", "nature": "ATTRIBUTION", "nature_libelle": "Avis d'attribution", "etat": "INITIAL", "url_avis": "https://boamp.test/b"},
                ]}
            return {"total_count": 3, "results": [
                {"idweb": "a", "objet": "Installation de filtres à eau", "dateparution": "2026-09-01", "datelimitereponse": "2026-09-10T12:00:00+00:00", "nomacheteur": "Ville A", "nature": "APPEL_OFFRE", "nature_libelle": "Avis de marché", "etat": "INITIAL", "url_avis": "https://boamp.test/a"},
            ]}

        result = collect(facts(), config(), now=datetime(2026, 9, 2, tzinfo=UTC), fetch=fetch, sleep=lambda _: None)
        self.assertEqual(result["collection_status"], "COMPLETED")
        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(result["summary"]["open_tenders_observed"], 1)
        self.assertEqual(result["summary"]["award_notices_observed"], 1)
        self.assertEqual(result["summary"]["principal_buyers"], [{"name": "Ville A", "notices": 2}])
        self.assertIsNone(result["observations"][0]["amount_eur"])
        self.assertIn("montant", result["summary"]["amounts"]["reason"])
        self.assertGreaterEqual(len(calls), 3)

    def test_empty_successful_responses_are_no_evidence(self):
        result = collect(facts(), config(), fetch=lambda *_: {"total_count": 0, "results": []}, sleep=lambda _: None)
        self.assertEqual(result["collection_status"], "NO_EVIDENCE")
        self.assertEqual(result["errors"], [])

    def test_all_network_failures_remain_unresolved(self):
        result = collect(facts(), config(), fetch=lambda *_: (_ for _ in ()).throw(TimeoutError("BOAMP indisponible")), sleep=lambda _: None)
        self.assertEqual(result["collection_status"], "UNRESOLVED")
        self.assertEqual(len(result["errors"]), 2)
        self.assertEqual(result["observations"], [])

    def test_refuses_facts_without_current_search_terms(self):
        input_facts = facts()
        input_facts.pop("keywords")
        input_facts.pop("affected_scope")
        with self.assertRaises(ValueError):
            collect(input_facts, config(), fetch=lambda *_: {"results": []}, sleep=lambda _: None)
