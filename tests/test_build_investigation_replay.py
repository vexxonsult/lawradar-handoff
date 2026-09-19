import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.build_investigation_replay import build


NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


def signal(signal_id, status="RETAINED", facts=True):
    return {
        "id": signal_id,
        "radar": {"status": status},
        "opportunity_facts": {"signal_id": signal_id, "title": "Décret test"} if facts else None,
        "source": {"source_id": "jorf:test"},
    }


def archive(signals):
    return {"schema": "lawradar-universal-signal-v2", "run": {"id": "run:test"}, "signals": signals}


class InvestigationReplayTests(unittest.TestCase):
    def test_selects_only_explicit_retained_archived_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "v2/2026/09/run-1.json"
            first.parent.mkdir(parents=True)
            first.write_text(json.dumps(archive([signal("signal:a"), signal("signal:discard", "DISCARDED")])), encoding="utf-8")
            result = build(root, ["signal:a"], now=NOW)
        self.assertEqual(result["schema"], "lawradar-universal-signal-v2")
        self.assertEqual([item["id"] for item in result["signals"]], ["signal:a"])
        self.assertEqual(result["run"]["kind"], "ARCHIVED_FACTS_REPLAY")
        self.assertTrue(result["run"]["archive_provenance"]["signal:a"].endswith("run-1.json"))

    def test_refuses_missing_or_non_fact_backed_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "archive.json"
            path.write_text(json.dumps(archive([signal("signal:empty", facts=False)])), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "faits versionnés"):
                build(root, ["signal:empty"], now=NOW)
            with self.assertRaisesRegex(ValueError, "introuvable"):
                build(root, ["signal:missing"], now=NOW)


if __name__ == "__main__":
    unittest.main()
