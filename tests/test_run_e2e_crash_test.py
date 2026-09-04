import json
import tempfile
import unittest
from pathlib import Path

from scripts.archive_universal_signal import validate_dossier
from scripts.run_e2e_crash_test import run


class EndToEndCrashTest(unittest.TestCase):
    def test_executes_the_isolated_chain_and_writes_each_decisive_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = run(output)
            self.assertEqual(report["verdict"], "PASS")
            self.assertTrue(report["scenario_only"])
            self.assertEqual(report["boamp_output"]["collection_status"], "COMPLETED")
            self.assertEqual(len(report["boamp_output"]["observations"]), 1)
            self.assertEqual(report["deterministic_filters"]["final_constraint"], "PASS")
            self.assertEqual(report["client_entrepreneur_delivery"]["status"], "READY_FOR_AI_ASSESSMENT")
            self.assertTrue((output / "universal-signal.json").exists())
            self.assertTrue((output / "client-entrepreneur-delivery.json").exists())
            dossier = json.loads((output / "universal-signal.json").read_text(encoding="utf-8"))
            validate_dossier(dossier)
            self.assertEqual(
                dossier["signals"][0]["reading_provenance"]["producer"],
                "SIMULATOR",
            )
            self.assertEqual(json.loads((output / "crash-test-report.json").read_text(encoding="utf-8"))["verdict"], "PASS")
