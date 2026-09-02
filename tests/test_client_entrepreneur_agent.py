import json
import tempfile
import unittest
from pathlib import Path

from scripts.clients.entrepreneur_agent import build_delivery, read_snapshot, source_hash


def dossier(with_gate=False):
    signal = {
        "id": "signal:1",
        "source": {"evidence": {"url": "https://official.test/a"}},
        "radar": {"status": "RETAINED", "reason": "Preuve officielle"},
        "enrichments": {
            "press": {"status": "COMPLETED", "result": {}},
            "demand": {"status": "COMPLETED", "result": {}},
            "market": {"status": "NO_EVIDENCE", "result": None},
        },
    }
    if with_gate:
        signal["deterministic_filters"] = {
            "final_constraint": "PASS",
            "operator_access": {"status": "PASS", "allow_external_collection": True},
        }
    return {"schema": "lawradar-universal-signal-v2", "signals": [signal], "money_flows": []}


class ClientEntrepreneurTests(unittest.TestCase):
    def test_waits_when_the_core_snapshot_has_no_filter_snapshot(self):
        value = build_delivery(dossier(), "hash", "signal:1")
        self.assertEqual(value["status"], "UNRESOLVED")
        self.assertIsNone(value["business_assessment"])
        self.assertTrue(any("filtres" in item for item in value["gaps"]))

    def test_becomes_ready_without_producing_a_business_assessment(self):
        value = build_delivery(dossier(with_gate=True), "hash", "signal:1")
        self.assertEqual(value["status"], "READY_FOR_AI_ASSESSMENT")
        self.assertIsNone(value["business_assessment"])
        self.assertFalse(value["execution"]["writes_to_core"])

    def test_reading_the_core_snapshot_does_not_change_its_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "universal-signal.json"
            raw = json.dumps(dossier(), ensure_ascii=False, indent=2).encode("utf-8")
            path.write_bytes(raw)
            snapshot, digest = read_snapshot(path)
            self.assertEqual(digest, source_hash(raw))
            self.assertEqual(snapshot["schema"], "lawradar-universal-signal-v2")
            self.assertEqual(path.read_bytes(), raw)

    def test_rejects_a_legacy_or_non_core_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.json"
            path.write_text('{"schema":"lawradar-universal-signal-v1"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_snapshot(path)

    def test_rejects_an_unknown_signal(self):
        with self.assertRaises(ValueError):
            build_delivery(dossier(), "hash", "signal:unknown")
