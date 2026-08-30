import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_primary_handoff import build_handoff


class PrimaryHandoffTests(unittest.TestCase):
    def test_keeps_only_uninterpreted_primary_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "documents").mkdir()
            (root / "manifest.json").write_text(json.dumps({"documents_found": ["JORFTEXT1"]}), encoding="utf-8")
            (root / "documents" / "JORFTEXT1.json").write_text(
                json.dumps({"text_id": "JORFTEXT1", "interpretation": None}), encoding="utf-8"
            )
            handoff = build_handoff(root)
            self.assertEqual(handoff["schema"], "lawradar-primary-handoff-v1")
            self.assertEqual(handoff["documents"][0]["text_id"], "JORFTEXT1")
            self.assertIsNone(handoff["interpretation"])
