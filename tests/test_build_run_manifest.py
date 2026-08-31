import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.build_run_manifest import build_manifest


class RunManifestTests(unittest.TestCase):
    def test_records_hashes_and_missing_files_without_exposing_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "input.json"
            existing.write_text('{"ok": true}\n', encoding="utf-8")
            manifest = build_manifest("motor", "success", [existing], [root / "missing.json"])
        self.assertEqual(manifest["schema"], "lawradar-run-manifest-v1")
        self.assertTrue(manifest["inputs"][0]["exists"])
        self.assertEqual(len(manifest["inputs"][0]["sha256"]), 64)
        self.assertFalse(manifest["outputs"][0]["exists"])
        self.assertNotIn('"ok": true', json.dumps(manifest))

    def test_uses_github_run_metadata_and_measures_duration(self):
        previous = {key: os.environ.get(key) for key in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "GITHUB_SHA", "LAWRADAR_STARTED_AT")}
        try:
            os.environ.update({"GITHUB_RUN_ID": "42", "GITHUB_REPOSITORY": "vexxonsult/lawradar-handoff", "GITHUB_SHA": "abc", "LAWRADAR_STARTED_AT": "1"})
            manifest = build_manifest("collector", "success", [], [])
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(manifest["run"]["id"], "42")
        self.assertGreaterEqual(manifest["run"]["duration_seconds"], 0)
        self.assertIn("/vexxonsult/lawradar-handoff/actions/runs/42", manifest["run"]["url"])
