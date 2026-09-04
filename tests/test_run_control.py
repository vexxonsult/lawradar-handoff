import unittest

from scripts.build_run_index import build_index, summarize_manifest
from scripts.render_control_dashboard import render_dashboard


def manifest(kind="collector"):
    return {
        "schema": "lawradar-run-manifest-v1",
        "run": {"kind": kind, "status": "success", "id": "12", "url": "https://example.test/run/12", "workflow": "test", "commit": "abc", "created_at_utc": "2026-09-01T10:00:00+00:00", "duration_seconds": 65},
        "inputs": [{"exists": True}],
        "outputs": [{"exists": True}, {"exists": False}],
        "cost_estimate": {"status": "not_reported_by_provider"},
        "errors": [],
        "retries": 0,
    }


class RunControlTests(unittest.TestCase):
    def test_summarizes_manifest_without_file_contents(self):
        summary = summarize_manifest(manifest())
        self.assertEqual(summary["inputs"], {"count": 1, "missing": 0})
        self.assertEqual(summary["outputs"], {"count": 2, "missing": 1})
        self.assertNotIn("xml_source", summary)

    def test_renders_safe_control_dashboard(self):
        index = {"schema": "lawradar-run-index-v1", "generated_at_utc": "2026-09-01T10:01:00+00:00", "runs": [summarize_manifest(manifest("motor"))]}
        html = render_dashboard(index)
        self.assertIn("Centre de contrôle LawRadar", html)
        self.assertIn("1 min 05 s", html)
        self.assertIn("ouvrir le run", html)

    def test_renders_skip_reason(self):
        item = summarize_manifest(manifest("motor"))
        item["reason"] = "EUR-Lex hors périmètre"
        html = render_dashboard({"schema": "lawradar-run-index-v1", "generated_at_utc": "2026-09-01T10:01:00+00:00", "runs": [item]})
        self.assertIn("EUR-Lex hors périmètre", html)

    def test_renders_visible_backlog_state(self):
        index = {"schema": "lawradar-run-index-v1", "generated_at_utc": "2026-09-01T10:01:00+00:00", "runs": []}
        backlog = {"schema": "lawradar-motor-backlog-v1", "status": "BACKLOG", "pending_count": 4, "batch_capacity": 250, "capacity_window": "PER_BATCH", "next_action": "RESUME_NEXT_BATCH_WINDOW"}
        html = render_dashboard(index, backlog)
        self.assertIn("BACKLOG", html)
        self.assertIn("4 candidat(s) en attente", html)

    def test_rejects_unknown_manifest(self):
        with self.assertRaises(ValueError):
            summarize_manifest({"schema": "other"})
