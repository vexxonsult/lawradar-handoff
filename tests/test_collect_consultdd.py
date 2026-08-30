import unittest

from scripts.collect_consultdd import records_from_html, search_url


class ConsultDDCollectorTests(unittest.TestCase):
    def test_builds_the_official_search_url_with_pagination(self):
        self.assertIn("page=recherche", search_url(20))
        self.assertIn("r_start=20", search_url(20))
        self.assertIn("recherche=consultation", search_url(20))

    def test_extracts_only_consultation_article_links_without_interpretation(self):
        page = '''<html><body>
          <div class="recherche-card"><div><h2><a href="prevention-des-risques-r6.html?debut_listearticles=96">Prévention des risques</a></h2><time datetime="2026-08-28">28 août</time></div></div>
          <a href="contacts-a75.html">Contact</a>
          <div class="recherche-card"><div><h2><a href="prevention-des-risques-r6.html?debut_listearticles=96">Doublon</a></h2></div></div>
        </body></html>'''
        records = records_from_html(page, "https://www.consultations-publiques.developpement-durable.gouv.fr/?page=recherche")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Prévention des risques")
        self.assertIn("prevention-des-risques", records[0]["url"])
        self.assertEqual(records[0]["dates"], ["2026-08-28"])
        self.assertIsNone(records[0]["interpretation"])
