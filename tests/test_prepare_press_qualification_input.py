import unittest

from scripts.prepare_press_qualification_input import build


class PreparePressQualificationInputTests(unittest.TestCase):
    def test_keeps_only_the_requested_signal_not_other_history(self):
        dossier = {
            "schema": "lawradar-universal-signal-v1",
            "signals": [
                {"id": "signal:current", "source": {"title": "Nouveau signal"}, "radar": {"status": "RETAINED"}, "enrichments": {}},
                {"id": "signal:old", "source": {"title": "Sibelco"}, "radar": {"status": "RETAINED"}, "enrichments": {}},
            ],
            "money_flows": [{"id": "old-flow"}],
        }
        candidates = {"schema": "lawradar-press-candidates-v1", "signal_id": "signal:current"}
        result = build(dossier, candidates)
        self.assertEqual(result["signal"]["id"], "signal:current")
        self.assertNotIn("Sibelco", str(result))
        self.assertNotIn("old-flow", str(result))
