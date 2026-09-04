"""Smoke tests for client commands invoked by the production workflow.

These scripts used to define ``main`` without calling it, so GitHub reported
success while producing no artifact.  Invoking their real CLI parser makes
that regression visible without any network access.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "scripts/prepare_opportunity_facts.py",
    "scripts/build_boamp_market_observations.py",
    "scripts/prepare_market_qualification_input.py",
    "scripts/build_market_terminal_enrichment.py",
)


class ClientCliEntrypointTests(unittest.TestCase):
    def test_each_workflow_client_command_executes_its_parser(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                result = subprocess.run(
                    [sys.executable, script, "--help"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())
