import unittest

from scripts.collect_consultdd import records_from_html, search_url


class ConsultDDCollectorTests(unittest.TestCase):
    def test_builds_the_official_search_url_with_pagination(self):
        self.assertIn("page=recherche", search_url(20))
        self.assertIn("r_start=20", search_url(20))
        self.assertIn("recherche=consultation", search_url(20))

    def test_extracts_only_consultation_article_links_without_interpretation(self):
        page = '''<html><body>
          <div class="recherche-card"><div><h2><a href="consultation-sur-un-projet-a100.html">Projet de consultation</a></h2><div class="recherche-card__start"><time datetime="2026-08-28">28 août</time></div></div></div>
          <a href="contacts-a75.html">Contact</a>
          <div class="recherche-card"><div><h2><a href="consultation-sur-un-projet-a100.html">Doublon</a></h2></div></div>
          <div class="recherche-card"><div><h2><a href="spip.php?page=sommaire">Consultations publiques</a></h2><time datetime="2026-08-28">28 août</time></div></div>
        </body></html>'''
        records = records_from_html(page, "https://www.consultations-publiques.developpement-durable.gouv.fr/?page=recherche")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Projet de consultation")
        self.assertIn("consultation-sur-un-projet", records[0]["url"])
        self.assertEqual(records[0]["dates"], ["2026-08-28"])
        self.assertIsNone(records[0]["interpretation"])
