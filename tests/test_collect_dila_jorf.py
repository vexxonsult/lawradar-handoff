import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.collect_dila_jorf import choose_archive, evidence_from_archive


def add_file(handle, name, payload):
    data = payload.encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(data)
    handle.addfile(info, io.BytesIO(data))


class CollectorTests(unittest.TestCase):
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
