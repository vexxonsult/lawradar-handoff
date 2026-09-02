import unittest
from datetime import UTC, datetime

from scripts.collect_press_candidates import collect


def dossier(status="RETAINED"):
    return {
        "schema": "lawradar-universal-signal-v1",
        "signals": [{
            "id": "signal:current",
            "source": {"evidence": {
                "title": "Arrêté relatif aux ombrières photovoltaïques",
                "official": {"title": "Arrêté du 2 septembre 2026 relatif aux ombrières photovoltaïques"},
            }},
            "radar": {"status": status},
            "enrichments": {},
        }],
    }


def config():
    return {
        "schema": "lawradar-press-agent-config-v1",
        "window_days_before": 14,
        "sources": {"gdelt_doc": {"enabled": True, "endpoint": "https://example.test/gdelt", "minimum_interval_seconds": 0, "max_records_per_query": 10}},
        "limits": {"max_queries_per_signal": 2, "max_candidates_per_signal": 15},
    }


class CollectPressCandidatesTests(unittest.TestCase):
    def test_collects_only_from_the_current_signal_and_deduplicates(self):
        calls = []

        def fetch(endpoint, params):
            calls.append((endpoint, params))
            return {"articles": [
                {"url": "http://journal.test/article?utm_source=x", "domain": "journal.test", "title": "Ombrières photovoltaïques : le nouvel arrêté", "seendate": "20260902T090000Z"},
                {"url": "https://journal.test/article", "domain": "journal.test", "title": "Ombrières photovoltaïques : le nouvel arrêté", "seendate": "20260902T090000Z"},
            ]}

        result = collect(dossier(), config(), "signal:current", now=datetime(2026, 9, 2, 12, tzinfo=UTC), fetch=fetch, sleep=lambda _: None)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("Sibelco", " ".join(call[1]["query"] for call in calls))
        self.assertEqual(result["candidates_total"], 4)
        self.assertEqual(result["candidates_after_dedup"], 1)
        self.assertEqual(result["candidates"][0]["excerpt"], None)

    def test_refuses_a_signal_not_retained_by_the_radar(self):
        with self.assertRaises(ValueError):
            collect(dossier("UNRESOLVED"), config(), "signal:current", fetch=lambda *_: {}, sleep=lambda _: None)

    def test_preserves_source_failure_for_later_unresolved_handling(self):
        def unavailable(*_):
            raise TimeoutError("timeout")

        result = collect(dossier(), config(), "signal:current", fetch=unavailable, sleep=lambda _: None)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(len(result["errors"]), 2)
        self.assertEqual(result["queries"][0]["hits"], None)
