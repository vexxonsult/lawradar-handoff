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
        "sources": {"gdelt_doc": {"enabled": True, "required": True, "endpoint": "https://example.test/gdelt", "minimum_interval_seconds": 0, "attempts_per_query": 1, "max_records_per_query": 10}, "publisher_rss": []},
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
        self.assertTrue(result["collection_successful"])

    def test_search_queries_do_not_reuse_truncated_titles_or_nested_quotes(self):
        input_data = dossier()
        input_data["signals"][0]["source"]["evidence"]["official"]["title"] = 'Arrêté sur le permis "Larchant"'
        result = collect(input_data, config(), "signal:current", fetch=lambda *_: {"articles": []}, sleep=lambda _: None)
        self.assertEqual(len(result["queries"]), 2)
        self.assertNotIn('"Larchant"', result["queries"][0]["query"])

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
        self.assertFalse(result["collection_successful"])

    def test_rss_is_matched_only_against_terms_from_the_current_signal(self):
        input_config = config()
        input_config["sources"]["gdelt_doc"] = {"enabled": False}
        input_config["sources"]["publisher_rss"] = [{
            "id": "localtis", "enabled": True, "required": True,
            "outlet": "Localtis", "source_kind": "editorial_institutional",
            "url": "https://example.test/localtis.xml", "minimum_matching_terms": 2,
        }]
        feed = """<?xml version='1.0'?><rss><channel>
        <item><title>Ombrières photovoltaïques : un arrêté publié</title><link>https://local.test/ombre?utm_source=rss</link><description>Les ombrières photovoltaïques sont concernées.</description><pubDate>Tue, 02 Sep 2026 09:00:00 GMT</pubDate></item>
        <item><title>Une carrière obtient une autorisation</title><link>https://local.test/other</link><description>Sans rapport avec le texte recherché.</description></item>
        </channel></rss>"""
        result = collect(dossier(), input_config, "signal:current", fetch_text=lambda _: feed, sleep=lambda _: None)
        self.assertTrue(result["collection_successful"])
        self.assertEqual(result["candidates_after_dedup"], 1)
        self.assertEqual(result["candidates"][0]["source"], "publisher-rss:localtis")
        self.assertEqual(result["candidates"][0]["url"], "https://local.test/ombre")
        self.assertNotIn("Sibelco", json_dump(result))

    def test_optional_gdelt_failure_does_not_invalidate_a_successful_required_rss(self):
        input_config = config()
        input_config["sources"]["gdelt_doc"]["required"] = False
        input_config["sources"]["publisher_rss"] = [{
            "id": "localtis", "enabled": True, "required": True,
            "outlet": "Localtis", "url": "https://example.test/localtis.xml", "minimum_matching_terms": 2,
        }]
        empty_feed = "<?xml version='1.0'?><rss><channel></channel></rss>"
        result = collect(dossier(), input_config, "signal:current", fetch=lambda *_: (_ for _ in ()).throw(TimeoutError("gdelt")), fetch_text=lambda _: empty_feed, sleep=lambda _: None)
        self.assertTrue(result["collection_successful"])
        self.assertEqual(len(result["errors"]), 2)
        self.assertEqual(result["required_errors"], [])

    def test_google_news_keeps_the_publisher_and_only_current_signal_terms(self):
        input_config = config()
        input_config["sources"]["gdelt_doc"] = {"enabled": False}
        input_config["sources"]["google_news_rss"] = {
            "enabled": True, "endpoint": "https://example.test/news", "language": "fr", "country": "FR", "edition": "FR:fr",
        }
        feed = """<?xml version='1.0'?><rss><channel>
        <item><title>Ombrières photovoltaïques : le nouvel arrêté</title><link>https://journal.test/a</link><source url='https://journal.test'>Journal test</source><description>Le nouvel arrêté sur les ombrières photovoltaïques.</description></item>
        <item><title>Photovoltaïque : une aide locale</title><link>https://journal.test/b</link><source url='https://journal.test'>Journal test</source><description>Une aide locale sans lien avec le nouvel arrêté.</description></item>
        </channel></rss>"""
        result = collect(dossier(), input_config, "signal:current", fetch_text=lambda _: feed, sleep=lambda _: None)
        self.assertTrue(result["collection_successful"])
        self.assertEqual(result["candidates_after_dedup"], 1)
        self.assertEqual(result["candidates"][0]["outlet"], "Journal test")
        self.assertEqual(result["candidates"][0]["source"], "publisher-rss:google-news-fr")


def json_dump(value):
    import json
    return json.dumps(value, ensure_ascii=False)
