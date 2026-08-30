import unittest

from scripts.collect_consultdd import records_from_html, search_url


class ConsultDDCollectorTests(unittest.TestCase):
    def test_builds_the_official_search_url_with_pagination(self):
        self.assertIn("page=recherche", search_url(20))
        self.assertIn("r_start=20", search_url(20))
        self.assertIn("recherche=consultation", search_url(20))

    def test_extracts_only_consultation_article_links_without_interpretation(self):
        page = '''<html><body>
          <a href="projet-d-arrete-a3401.html?lang=fr">Projet d’arrêté CEE</a>
          <a href="/spip.php?page=plan">Plan</a>
          <a href="projet-d-arrete-a3401.html?lang=fr">Doublon</a>
        </body></html>'''
        records = records_from_html(page, "https://www.consultations-publiques.developpement-durable.gouv.fr/?page=recherche")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["consultation_id"], "a3401")
        self.assertEqual(records[0]["title"], "Projet d’arrêté CEE")
        self.assertIsNone(records[0]["interpretation"])
