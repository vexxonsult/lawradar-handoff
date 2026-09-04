import unittest
from pathlib import Path


WORKFLOWS = {
    "press": Path(".github/workflows/agent-presse-lawradar.yml"),
    "demand_market": Path(".github/workflows/agent-marche-boamp-lawradar.yml"),
}


class ManualAgentWorkflowTests(unittest.TestCase):
    def test_manual_agents_are_read_only_spokes(self):
        for name, path in WORKFLOWS.items():
            with self.subTest(workflow=name):
                workflow = path.read_text(encoding="utf-8")
                self.assertIn("permissions:\n  contents: read", workflow)
                self.assertIn("evidence/universal-signal-latest.json", workflow)
                self.assertNotIn("persist_core", workflow)
                self.assertNotIn("scripts/merge_agent_enrichment.py", workflow)
                self.assertNotIn("git add", workflow)
                self.assertNotIn("git commit", workflow)
                self.assertNotIn("git push", workflow)
                self.assertNotIn("group: lawradar-evidence-writer", workflow)
                self.assertNotIn("universal-signal-enriched.json", workflow)

    def test_manual_agents_publish_only_separate_enrichment_artifacts(self):
        press = WORKFLOWS["press"].read_text(encoding="utf-8")
        demand_market = WORKFLOWS["demand_market"].read_text(encoding="utf-8")
        self.assertIn("out/press-enrichment.json", press)
        self.assertIn("name: lawradar-press-", press)
        self.assertIn("out/demand-enrichment.json", demand_market)
        self.assertIn("out/market-enrichment.json", demand_market)
        self.assertIn("name: lawradar-demand-market-boamp-", demand_market)


if __name__ == "__main__":
    unittest.main()
