import unittest

from scripts.enrich_jorf_candidates import MAX_EXCERPT_CHARS, archive_lookup, excerpt_entry


class EnrichJorfCandidatesTests(unittest.TestCase):
    def test_maps_a_text_to_its_official_archive(self):
        summary = {"editions": [{"archive_url": "https://dila.test/archive.tar.gz", "documents": [{"text_id": "JORFTEXT1"}]}]}
        self.assertEqual(archive_lookup(summary), {"JORFTEXT1": "https://dila.test/archive.tar.gz"})

    def test_keeps_a_bounded_primary_excerpt_and_its_hash(self):
        text = "x" * (MAX_EXCERPT_CHARS + 1)
        document = {
            "text_id": "JORFTEXT1", "archive_url": "https://dila.test/archive.tar.gz", "archive_sha256": "archive",
            "articles": [{"plain_text": text}],
        }
        result = excerpt_entry(document)
        self.assertEqual(result["content_status"], "AVAILABLE")
        self.assertEqual(len(result["official_text_excerpt"]), MAX_EXCERPT_CHARS)
        self.assertTrue(result["excerpt_truncated"])
        self.assertTrue(result["official_text_sha256"])
        self.assertIn("passage central", result["official_text_excerpt"])
