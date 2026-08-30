import unittest

from scripts.collect_eurlex_oj import build_query, records_from_response


class EurlexCollectorTests(unittest.TestCase):
    def test_query_is_bounded_by_the_requested_dates(self):
        query = build_query("2026-08-19", "2026-08-29")
        self.assertIn('"2026-08-19"^^xsd:date', query)
        self.assertIn('"2026-08-29"^^xsd:date', query)
        self.assertIn("cdm:official-journal_class", query)

    def test_keeps_only_l_series_and_preserves_raw_metadata(self):
        response = {"results": {"bindings": [
            {"uri": {"value": "http://publications.europa.eu/resource/cellar/l"}, "ojclass": {"value": "http://publications.europa.eu/resource/authority/oj-type/L"}, "ojnumber": {"value": "200"}, "ojcollection": {"value": "OJ"}, "ojyear": {"value": "2026"}, "workdatedoc": {"value": "2026-08-29"}},
            {"uri": {"value": "http://publications.europa.eu/resource/cellar/c"}, "ojclass": {"value": "http://publications.europa.eu/resource/authority/oj-type/C"}, "ojnumber": {"value": "201"}, "ojcollection": {"value": "OJ"}, "ojyear": {"value": "2026"}, "workdatedoc": {"value": "2026-08-29"}},
        ]}}
        records = records_from_response(response)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["official_journal_number"], "200")
        self.assertIsNone(records[0]["interpretation"])
