import unittest

from scripts.collect_consultdd import attachment_links_from_html, official_detail_from_html, records_from_html, search_url


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

    def test_extracts_visible_official_detail(self):
        page = '''<h1>Consultation officielle</h1>
        <div class="date-article"><p>Consultation du 01/09/2026 au 15/09/2026</p></div>
        <div class="texte-article"><p>La société X sollicite une autorisation.</p></div>
        <div class="listedocuments">documents</div>'''
        detail = official_detail_from_html(page)
        self.assertEqual(detail["official_title"], "Consultation officielle")
        self.assertIn("société X", detail["official_text"])

    def test_keeps_only_camino_download_attachments(self):
        page = '''<a href="https://camino.beta.gouv.fr/apiUrl/download/fichiers/a">Dossier</a>
        <a href="https://example.test/other">Autre</a>'''
        self.assertEqual(attachment_links_from_html(page, "https://example.test"), [{
            "url": "https://camino.beta.gouv.fr/apiUrl/download/fichiers/a", "label": "Dossier"
        }])
