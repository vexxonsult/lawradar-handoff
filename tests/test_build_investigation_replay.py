import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_investigation_replay import build


def archive(signal_status: str) -> dict:
    return {
        "schema": "lawradar-universal-signal-v2",
        "signals": [{
            "id": "signal:cee",
            "radar": {"status": signal_status},
            "opportunity_facts": {"title": "Projet CEE"},
        }],
    }


class InvestigationReplayTests(unittest.TestCase):
    def test_replays_last_retained_snapshot_when_later_archive_discards_same_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "2026-09-28.json").write_text(json.dumps(archive("RETAINED")), encoding="utf-8")
            (root / "2026-09-29.json").write_text(json.dumps(archive("DISCARDED")), encoding="utf-8")

            result = build(root, ["signal:cee"])

        self.assertEqual(result["signals"][0]["id"], "signal:cee")
        self.assertEqual(result["signals"][0]["radar"]["status"], "RETAINED")
        self.assertEqual(result["run"]["kind"], "ARCHIVED_FACTS_REPLAY")


if __name__ == "__main__":
    unittest.main()
