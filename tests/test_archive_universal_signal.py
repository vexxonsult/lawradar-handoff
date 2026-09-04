import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.archive_universal_signal import archive_dossier


def dossier(run_id="42"):
    return {
        "schema": "lawradar-universal-signal-v2",
        "run": {
            "id": run_id, "attempt": None,
            "url": "https://example.test/run/42", "commit": "abc",
            "report_date": "2026-09-04",
        },
        "context": {"prefilter_audit": {
            "excluded_historical_candidates": [],
            "excluded_routine_candidates": [],
            "excluded_no_economic_friction_candidates": [],
            "deterministically_unresolved_candidates": [],
        }},
        "signals": [{
            "id": "signal:daily",
            "identity": {
                "stable_source_id": "source:stable",
                "evidence_version": "sha256:" + "a" * 64,
            },
            "source": {
                "source_id": "jorf:JORFTEXT1", "source_kind": "JORF",
                "change": "NEW", "evidence": None,
            },
            "radar": {"status": "RETAINED", "reason": "Preuve."},
            "reading": {
                "consequence": "Une règle change.", "affected_actors": [],
                "beneficiaries": [], "constrained_parties": [],
                "potential_service_partners": [], "unknowns": [],
            },
            "reading_provenance": {
                "status": "AVAILABLE", "basis": "CANDIDATE_EVIDENCE_ONLY",
                "producer": "MOTOR_STRUCTURED_READING", "source_id": "jorf:JORFTEXT1",
            },
            "opportunity_facts": {
                "schema": "lawradar-opportunity-facts-v1",
                "signal_id": "signal:daily", "title": "Texte",
                "keywords": ["texte"], "affected_scope": ["France"],
                "legal": {
                    "jurisdiction": "FR", "text_status": "PUBLISHED",
                    "proof_status": "VERIFIED", "effective_date": None,
                    "affected_scope": ["France"],
                },
                "requirements": {
                    "required_capabilities": [], "required_authorizations": [],
                    "dependencies": [], "minimum_startup_capital_eur": None,
                    "estimated_time_to_market_weeks": None,
                    "evidence_status": "MISSING",
                },
            },
            "enrichments": {},
        }],
        "money_flows": [],
        "quality": {
            "opportunity_count": 1, "unresolved_count": 0,
            "readings_available_count": 1, "evidence_reference_count": 0,
            "money_flow_count": 0, "money_flow_unlinked_count": 0,
            "limitation": "Test.",
        },
    }


class UniversalSignalArchiveTests(unittest.TestCase):
    def write_dossier(self, root, value):
        path = root / "out" / "universal-signal.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def test_creates_an_immutable_snapshot_and_exact_latest_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_dossier(root, dossier())
            manifest = archive_dossier(
                source, root / "evidence" / "universal-signals",
                root / "evidence" / "universal-signal-latest.json",
                root / "out" / "archive-manifest.json",
            )
            archive = Path(manifest["archive_path"])
            self.assertEqual(manifest["status"], "CREATED")
            self.assertEqual(archive, root / "evidence/universal-signals/v2/2026/09/run-42.json")
            self.assertTrue(Path(manifest["durable_manifest_path"]).exists())
            self.assertEqual(archive.read_bytes(), source.read_bytes())
            self.assertEqual((root / "evidence/universal-signal-latest.json").read_bytes(), source.read_bytes())
            self.assertEqual(manifest["signals"][0]["stable_source_id"], "source:stable")

    def test_same_run_and_same_bytes_is_an_idempotent_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_dossier(root, dossier())
            arguments = (
                source, root / "evidence" / "universal-signals",
                root / "evidence" / "universal-signal-latest.json",
                root / "out" / "archive-manifest.json",
            )
            archive_dossier(*arguments)
            second = archive_dossier(*arguments)
            self.assertEqual(second["status"], "NOOP")

    def test_archive_only_does_not_replace_the_latest_client_core(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_dossier(root, dossier())
            latest = root / "evidence" / "universal-signal-latest.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_text('{"existing":"client-core"}\n', encoding="utf-8")

            manifest = archive_dossier(
                source, root / "evidence" / "universal-signals", None,
                root / "out" / "archive-manifest.json",
            )

            self.assertIsNone(manifest["latest_path"])
            self.assertEqual(latest.read_text(encoding="utf-8"), '{"existing":"client-core"}\n')
            self.assertTrue(Path(manifest["archive_path"]).exists())

    def test_refuses_to_overwrite_a_run_with_different_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_dossier(root, dossier())
            arguments = (
                source, root / "evidence" / "universal-signals",
                root / "evidence" / "universal-signal-latest.json",
                root / "out" / "archive-manifest.json",
            )
            archive_dossier(*arguments)
            changed = copy.deepcopy(dossier())
            changed["signals"][0]["radar"]["status"] = "DISCARDED"
            self.write_dossier(root, changed)
            with self.assertRaisesRegex(ValueError, "IMMUTABILITY_VIOLATION"):
                archive_dossier(*arguments)

    def test_two_runs_on_the_same_day_create_two_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_root = root / "evidence" / "universal-signals"
            latest = root / "evidence" / "universal-signal-latest.json"
            manifest = root / "out" / "archive-manifest.json"
            first = self.write_dossier(root, dossier("42"))
            first_result = archive_dossier(first, archive_root, latest, manifest)
            second = self.write_dossier(root, dossier("43"))
            second_result = archive_dossier(second, archive_root, latest, manifest)
            self.assertNotEqual(first_result["archive_path"], second_result["archive_path"])
            self.assertTrue(Path(first_result["archive_path"]).exists())
            self.assertTrue(Path(second_result["archive_path"]).exists())

    def test_a_github_rerun_uses_its_attempt_in_the_immutable_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_root = root / "evidence" / "universal-signals"
            latest = root / "evidence" / "universal-signal-latest.json"
            manifest = root / "out" / "archive-manifest.json"
            first_value = dossier("42")
            first_value["run"]["attempt"] = "1"
            first = self.write_dossier(root, first_value)
            first_result = archive_dossier(first, archive_root, latest, manifest)
            second_value = dossier("42")
            second_value["run"]["attempt"] = "2"
            second_value["signals"][0]["radar"]["reason"] = "Rejeu légitime."
            second = self.write_dossier(root, second_value)
            second_result = archive_dossier(second, archive_root, latest, manifest)
            self.assertTrue(first_result["archive_path"].endswith("run-42-attempt-1.json"))
            self.assertTrue(second_result["archive_path"].endswith("run-42-attempt-2.json"))

    def test_rejects_a_structurally_invalid_v2_before_archiving(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = dossier()
            invalid["signals"][0]["identity"]["evidence_version"] = "sha256:evidence"
            source = self.write_dossier(root, invalid)
            with self.assertRaisesRegex(ValueError, "version de preuve"):
                archive_dossier(
                    source, root / "archives", root / "latest.json", root / "manifest.json"
                )

    def test_rejects_a_path_traversal_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_dossier(root, dossier("../../escape"))
            with self.assertRaisesRegex(ValueError, "dangereux"):
                archive_dossier(
                    source, root / "archives", root / "latest.json", root / "manifest.json"
                )

    def test_accepts_an_explicitly_isolated_simulator_reading(self):
        simulated = dossier()
        simulated["context"]["scenario_only"] = True
        simulated["signals"][0]["source"]["source_kind"] = "SIMULATION"
        simulated["signals"][0]["reading_provenance"]["producer"] = "SIMULATOR"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_dossier(root, simulated)
            result = archive_dossier(
                source, root / "archives", root / "latest.json", root / "manifest.json"
            )
            self.assertEqual(result["status"], "CREATED")

    def test_rejects_a_simulator_reading_in_a_production_dossier(self):
        simulated = dossier()
        simulated["signals"][0]["reading_provenance"]["producer"] = "SIMULATOR"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_dossier(root, simulated)
            with self.assertRaisesRegex(ValueError, "simulée.*production"):
                archive_dossier(
                    source, root / "archives", root / "latest.json", root / "manifest.json"
                )

    def test_generic_v2_schema_keeps_new_money_flow_links_optional(self):
        schema_path = Path(__file__).parents[1] / "config/universal-signal-schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        required = set(schema["$defs"]["moneyFlow"]["required"])
        self.assertTrue({"source_id", "signal_id", "link_status"}.isdisjoint(required))

    def test_durable_archive_requires_money_flow_links(self):
        value = dossier()
        value["money_flows"] = [{
            "id": "MF-01-01", "label": "Flux", "title": "Paiement",
            "money_sentence": "A paie B.", "explanation": "Preuve.",
            "payer": "A", "recipient": "B", "amount": "100 EUR",
            "effective_date": "2026-09-04", "certainty": "VERIFIED",
            "next_action": "Contrôler.",
        }]
        value["quality"]["money_flow_count"] = 1
        value["quality"]["money_flow_unlinked_count"] = 1
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write_dossier(root, value)
            with self.assertRaisesRegex(ValueError, "Statut de liaison"):
                archive_dossier(
                    source, root / "archives", root / "latest.json", root / "manifest.json"
                )
