import datetime as dt
import unittest

from scripts.collect_eurlex_oj import daily_view_url, records_from_html


class EurlexCollectorTests(unittest.TestCase):
    def test_builds_the_official_daily_view_for_a_date(self):
        url = daily_view_url(dt.date(2026, 8, 21))
        self.assertIn("ojDate=21082026", url)
        self.assertIn("daily-view/L-series", url)

    def test_extracts_l_series_acts_without_interpretation(self):
        page = '''<html><body>
          <a href="./../../../legal-content/EN/TXT/?uri=OJ:L_202601960">Commission Implementing Regulation (EU) 2026/1960</a>
          <a href="./../../../legal-content/EN/TXT/?uri=OJ:C_202600001">Information notice</a>
        </body></html>'''
        records = records_from_html(page, "https://eur-lex.europa.eu/oj/daily-view/L-series/default.html?ojDate=21082026", "2026-08-21")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["official_journal_id"], "OJ:L_202601960")
        self.assertEqual(records[0]["title"], "Commission Implementing Regulation (EU) 2026/1960")
        self.assertIsNone(records[0]["interpretation"])
