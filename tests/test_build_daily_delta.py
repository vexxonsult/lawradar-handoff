import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_daily_delta import build_delta


class DailyDeltaTests(unittest.TestCase):
    def write(self, directory, name, payload):
        (directory / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_ignores_collection_timestamps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); previous = root / "previous"; current = root / "current"
            previous.mkdir(); current.mkdir()
            self.write(previous, "primary-evidence-latest.json", {"documents": [], "collected_at_utc": "2026-08-29T00:00:00Z"})
            self.write(current, "primary-evidence-latest.json", {"documents": [], "collected_at_utc": "2026-08-30T00:00:00Z"})
            delta = build_delta(previous, current)
            self.assertEqual(delta["sources"][0]["status"], "UNCHANGED")
            self.assertFalse(delta["model_input_required"])

    def test_marks_unsupported_eurlex_change_without_requesting_the_current_motor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); previous = root / "previous"; current = root / "current"
            previous.mkdir(); current.mkdir()
            self.write(previous, "eurlex-oj-latest.json", {"documents": [{"id": "A"}]})
            self.write(current, "eurlex-oj-latest.json", {"documents": [{"id": "A"}, {"id": "B"}]})
            delta = build_delta(previous, current)
            source = next(item for item in delta["sources"] if item["file"] == "eurlex-oj-latest.json")
            self.assertEqual(source["status"], "CHANGED")
            self.assertEqual(source["item_count"], 2)
            self.assertTrue(delta["evidence_change_detected"])
            self.assertFalse(delta["model_input_required"])
            self.assertFalse(delta["supported_model_change_detected"])

    def test_requires_model_input_for_a_supported_jorf_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); previous = root / "previous"; current = root / "current"
            previous.mkdir(); current.mkdir()
            self.write(previous, "jorf-summaries-latest.json", {"editions": [{"documents": [{"text_id": "A"}]}]})
            self.write(current, "jorf-summaries-latest.json", {"editions": [{"documents": [{"text_id": "A"}, {"text_id": "B"}]}]})
            delta = build_delta(previous, current)
            self.assertTrue(delta["evidence_change_detected"])
            self.assertTrue(delta["model_input_required"])
            self.assertEqual(delta["supported_changed_sources"], ["jorf-summaries-latest.json"])

    def test_marks_a_coverage_date_change_without_new_documents_as_metadata_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); previous = root / "previous"; current = root / "current"
            previous.mkdir(); current.mkdir()
            self.write(previous, "jorf-summaries-latest.json", {"coverage_end": "2026-08-29", "editions": [{"documents": [{"text_id": "JORFTEXT1"}]}]})
            self.write(current, "jorf-summaries-latest.json", {"coverage_end": "2026-08-30", "editions": [{"documents": [{"text_id": "JORFTEXT1"}]}]})
            delta = build_delta(previous, current)
            source = next(item for item in delta["sources"] if item["file"] == "jorf-summaries-latest.json")
            self.assertEqual(source["status"], "METADATA_CHANGED")
            self.assertFalse(delta["model_input_required"])
