import json
import tempfile
import unittest
from pathlib import Path

from scripts.promote_public_handoff import promote


class PromotePublicHandoffTests(unittest.TestCase):
    def test_empty_candidate_does_not_replace_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            current = root / "current.json"
            candidate_evidence = root / "candidate"
            current_evidence = root / "latest"
            candidate_evidence.mkdir()
            current_evidence.mkdir()
            candidate.write_text(json.dumps({"manifest": {"documents_found": []}, "documents": []}), encoding="utf-8")
            current.write_text("stable", encoding="utf-8")
            (current_evidence / "proof.json").write_text("stable", encoding="utf-8")

            promoted = promote(candidate, candidate_evidence, current, current_evidence, root / "status.json")

            self.assertFalse(promoted)
            self.assertEqual(current.read_text(encoding="utf-8"), "stable")
            self.assertEqual((current_evidence / "proof.json").read_text(encoding="utf-8"), "stable")
            self.assertFalse(json.loads((root / "status.json").read_text(encoding="utf-8"))["promoted"])

    def test_non_empty_candidate_replaces_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.json"
            current = root / "current.json"
            candidate_evidence = root / "candidate"
            current_evidence = root / "latest"
            candidate_evidence.mkdir()
            current_evidence.mkdir()
            payload = {"manifest": {"documents_found": ["JORFTEXT1"]}, "documents": [{"text_id": "JORFTEXT1"}]}
            candidate.write_text(json.dumps(payload), encoding="utf-8")
            current.write_text("old", encoding="utf-8")
            (candidate_evidence / "manifest.json").write_text("new", encoding="utf-8")
            (current_evidence / "old.json").write_text("old", encoding="utf-8")

            promoted = promote(candidate, candidate_evidence, current, current_evidence, root / "status.json")

            self.assertTrue(promoted)
            self.assertEqual(json.loads(current.read_text(encoding="utf-8")), payload)
            self.assertFalse((current_evidence / "old.json").exists())
            self.assertEqual((current_evidence / "manifest.json").read_text(encoding="utf-8"), "new")


if __name__ == "__main__":
    unittest.main()
