import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_client_branch


class ResearchOnlyClientBranchTests(unittest.TestCase):
    def test_press_branch_passes_the_explicit_research_switch_to_all_selectors(self):
        calls = []

        def fake_run(*args):
            calls.append(args)

        def fake_load(path):
            if path.name == "deterministic-filters.json":
                return {"operator_access": {"allow_external_collection": True}}
            return {"candidates": [], "collection_successful": True, "errors": []}

        with patch.object(run_client_branch, "_run", fake_run), patch.object(run_client_branch, "_load", fake_load):
            run_client_branch._press(Path("core.json"), "signal:research", Path("out/test"), "claude-sonnet-5", "standard", True)

        selector_calls = [call for call in calls if call[0] in {
            "scripts/prepare_opportunity_facts.py", "scripts/collect_press_candidates.py"
        }]
        self.assertEqual(len(selector_calls), 2)
        self.assertTrue(all("--allow-research-candidate" in call for call in selector_calls))

    def test_market_branch_passes_the_explicit_research_switch_to_facts_extractor(self):
        calls = []

        def fake_run(*args):
            calls.append(args)

        def fake_load(path):
            if path.name == "deterministic-filters.json":
                return {"operator_access": {"allow_external_collection": True}}
            return {"collection_status": "COMPLETED", "observations": []}

        with patch.object(run_client_branch, "_run", fake_run), patch.object(run_client_branch, "_load", fake_load):
            run_client_branch._demand_market(Path("core.json"), "signal:research", Path("out/test"), "claude-sonnet-5", True)

        self.assertIn("--allow-research-candidate", calls[0])

