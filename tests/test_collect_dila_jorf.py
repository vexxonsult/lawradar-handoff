import io
import json
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.collect_dila_jorf import archive_url_for, choose_archive, evidence_from_archive, summary_from_archive, text_payload, write_summaries


def add_file(handle, name, payload):
    data = payload.encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(data)
    handle.addfile(info, io.BytesIO(data))


class CollectorTests(unittest.TestCase):
    def test_keeps_every_text_block_in_an_official_article(self):
        root = ET.fromstring(
            "<ARTICLE><BLOC_TEXTUEL><CONTENU><p>Visa.</p></CONTENU></BLOC_TEXTUEL>"
            "<BLOC_TEXTUEL><CONTENU><p>Article 1 : 500 euros.</p></CONTENU></BLOC_TEXTUEL></ARTICLE>"
        )
        self.assertEqual(text_payload(root), "Visa.\nArticle 1 : 500 euros.")

    def test_builds_an_archive_url_without_listing_query(self):
        url = archive_url_for(
            "https://echanges.dila.gouv.fr/OPENDATA/JORF?C=M;O=D",
            "JORF_20260830-214758.tar.gz",
        )
        self.assertEqual(url, "https://echanges.dila.gouv.fr/OPENDATA/JORF/JORF_20260830-214758.tar.gz")

    def test_uses_latest_delivery_for_requested_day(self):
        archive = choose_archive([
            ("20260828", "002000", "JORF_20260828-002000.tar.gz"),
            ("20260828", "214758", "JORF_20260828-214758.tar.gz"),
        ], "2026-08-28")
        self.assertEqual(archive[2], "JORF_20260828-214758.tar.gz")

    def test_writes_primary_evidence_without_interpretation(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            archive = tmp_path / "fixture.tar.gz"
            text_id = "JORFTEXT000000000001"
            article_id = "JORFARTI000000000001"
            with tarfile.open(archive, "w:gz") as handle:
                add_file(handle, f"text/{text_id}.xml", f"""<TEXTELR><META><META_COMMUN><NATURE>DECRET</NATURE></META_COMMUN><META_SPEC><META_TEXTE_CHRONICLE><NOR>TEST0001D</NOR><DATE_PUBLI>2026-08-28</DATE_PUBLI><NUM_PARUTION>0200</NUM_PARUTION></META_TEXTE_CHRONICLE></META_SPEC></META><STRUCT><LIEN_ART id=\"{article_id}\" /></STRUCT></TEXTELR>""")
                add_file(handle, f"article/{article_id}.xml", "<ARTICLE><CONTEXTE><TEXTE><TITRE_TXT>Décret de test</TITRE_TXT></TEXTE></CONTEXTE><BLOC_TEXTUEL><CONTENU><p>Texte primaire.</p></CONTENU></BLOC_TEXTUEL></ARTICLE>")

            manifest = evidence_from_archive(archive, "https://example.test/fixture.tar.gz", {text_id}, tmp_path / "out")
            self.assertEqual(manifest["documents_found"], [text_id])
            self.assertIsNone(manifest["interpretation"])
            document = json.loads((tmp_path / "out" / "documents" / f"{text_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(document["title"], "Décret de test")
            self.assertEqual(document["articles"][0]["plain_text"], "Texte primaire.")
            self.assertIsNone(document["interpretation"])

    def test_writes_text_version_when_archive_has_no_article_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            archive = tmp_path / "fixture.tar.gz"
            text_id = "JORFTEXT000000000002"
            with tarfile.open(archive, "w:gz") as handle:
                add_file(handle, f"text/{text_id}.xml", "<TEXTE_VERSION><META><META_COMMUN><NATURE>ARRETE</NATURE></META_COMMUN><META_SPEC><META_TEXTE_CHRONICLE><DATE_PUBLI>2026-08-28</DATE_PUBLI></META_TEXTE_CHRONICLE><META_TEXTE_VERSION><TITREFULL>Arrêté de test</TITREFULL></META_TEXTE_VERSION></META_SPEC></META><VISAS><CONTENU><p>Texte primaire versionné.</p></CONTENU></VISAS></TEXTE_VERSION>")
            evidence_from_archive(archive, "https://example.test/fixture.tar.gz", {text_id}, tmp_path / "out")
            document = json.loads((tmp_path / "out" / "documents" / f"{text_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(document["title"], "Arrêté de test")
            self.assertEqual(document["articles"][0]["plain_text"], "Texte primaire versionné.")

    def test_builds_an_uninterpreted_primary_edition_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            archive = tmp_path / "fixture.tar.gz"
            text_id = "JORFTEXT000000000003"
            article_id = "JORFARTI000000000003"
            with tarfile.open(archive, "w:gz") as handle:
                add_file(handle, f"text/{text_id}.xml", f"""<TEXTELR><META><META_COMMUN><NATURE>DECRET</NATURE></META_COMMUN><META_SPEC><META_TEXTE_CHRONICLE><NOR>TEST0003D</NOR><DATE_PUBLI>2026-08-29</DATE_PUBLI><NUM_PARUTION>0201</NUM_PARUTION></META_TEXTE_CHRONICLE></META_SPEC></META><STRUCT><LIEN_ART id=\"{article_id}\" /></STRUCT></TEXTELR>""")
                add_file(handle, f"article/{article_id}.xml", "<ARTICLE><CONTEXTE><TEXTE><TITRE_TXT>Décret de sommaire</TITRE_TXT></TEXTE></CONTEXTE></ARTICLE>")

            summary = summary_from_archive(archive, "https://example.test/fixture.tar.gz")
            self.assertEqual(summary["schema"], "lawradar-primary-jorf-edition-v1")
            self.assertIsNone(summary["interpretation"])
            self.assertEqual(summary["documents"][0]["text_id"], text_id)
            self.assertEqual(summary["documents"][0]["title"], "Décret de sommaire")
            self.assertIsNone(summary["documents"][0]["interpretation"])

    def test_marks_a_missing_day_as_partial_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            archive = tmp_path / "JORF_20260817-214758.tar.gz"
            with tarfile.open(archive, "w:gz"):
                pass

            def fake_fetch(url, destination=None):
                destination.write_bytes(archive.read_bytes())
                return None

            from unittest.mock import patch

            with patch("scripts.collect_dila_jorf.fetch", fake_fetch):
                summary = write_summaries(
                    [("20260817", "214758", archive.name)],
                    "https://echanges.dila.gouv.fr/OPENDATA/JORF?C=M;O=D",
                    "2026-08-17",
                    "2026-08-18",
                    tmp_path / "summary.json",
                )

            self.assertEqual(summary["status"], "PRIMARY_ARCHIVE_PARTIAL")
            self.assertEqual(summary["covered_dates"], ["2026-08-17"])
            self.assertEqual(summary["missing_dates"], ["2026-08-18"])
