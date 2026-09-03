import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_anthropic_motor_batch import (
    MAX_CANDIDATES,
    assemble_delivery,
    anthropic_output_schema,
    build_requests,
    run_batch,
    validate_motor_input,
)


def candidate(source_id="jorf:ONE", title="Texte un"):
    return {
        "source_id": source_id,
        "source_kind": "JORF",
        "change": "NEW",
        "evidence": {
            "text_id": source_id.split(":", 1)[-1],
            "title": title,
            "publication_date": "2026-09-03",
            "official_text_excerpt": "Le ministre arrête une mesure démontrée.",
        },
    }


def motor_input(*candidates):
    return {
        "schema": "lawradar-motor-input-v1",
        "report_date": "2026-09-03",
        "candidates": list(candidates) or [candidate()],
    }


def result_value(source_id):
    return {
        "source_id": source_id,
        "status": "UNRESOLVED",
        "reason": "Aucun flux financier démontré dans l'extrait.",
        "facts": {
            "schema": "lawradar-opportunity-facts-v1",
            "signal_id": source_id,
            "title": "Texte officiel",
            "keywords": ["mesure démontrée"],
            "affected_scope": ["France"],
            "legal": {
                "jurisdiction": "FR",
                "text_status": "PUBLISHED",
                "proof_status": "PARTIAL",
                "effective_date": None,
                "affected_scope": ["France"],
            },
            "requirements": {
                "required_capabilities": [],
                "required_authorizations": [],
                "dependencies": [],
                "minimum_startup_capital_eur": None,
                "estimated_time_to_market_weeks": None,
                "evidence_status": "MISSING",
            },
            "operator_access": {
                "sector": "NOT_CLASSIFIED",
                "direct_offer_status": "NOT_APPLICABLE",
                "peripheral_role_evidence": "NOT_APPLICABLE",
                "evidence_status": "MISSING",
                "peripheral_service_evidence": [],
            },
        },
        "money_flows": [],
    }


class FakeBatches:
    def __init__(self, responses, *, starts_ended=True):
        self.responses = responses
        self.starts_ended = starts_ended
        self.created = []
        self.retrieved = []

    def batch(self, status):
        return {
            "id": "msgbatch_test",
            "processing_status": status,
            "request_counts": {
                "processing": 0 if status == "ended" else len(self.responses),
                "succeeded": len(self.responses) if status == "ended" else 0,
                "errored": 0,
                "canceled": 0,
                "expired": 0,
            },
        }

    def create(self, **kwargs):
        self.created.append(kwargs)
        return self.batch("ended" if self.starts_ended else "in_progress")

    def retrieve(self, batch_id):
        self.retrieved.append(batch_id)
        return self.batch("ended" if self.starts_ended else "in_progress")

    def results(self, batch_id):
        return self.responses


class FakeClient:
    def __init__(self, responses, *, starts_ended=True):
        self.messages = type("Messages", (), {})()
        self.messages.batches = FakeBatches(responses, starts_ended=starts_ended)


def response(custom_id, source_id):
    return {
        "custom_id": custom_id,
        "result": {
            "type": "succeeded",
            "message": {
                "content": [{"type": "text", "text": json.dumps(result_value(source_id))}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        },
    }


class AnthropicMotorBatchTests(unittest.TestCase):
    def test_workflow_keeps_the_bounded_candidate_gate_and_removes_agent_turns(self):
        workflow = Path(".github/workflows/moteur-lawradar.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count(f"--batch-size {MAX_CANDIDATES}"), 2)
        self.assertEqual(workflow.count("--active-batch-state evidence/motor-batch-latest.json"), 2)
        self.assertIn("scripts/run_anthropic_motor_batch.py", workflow)
        self.assertNotIn("anthropics/claude-code-action", workflow)
        self.assertNotIn("--max-turns", workflow)

    def test_workflow_uses_paris_time_and_automatic_client_fanout(self):
        motor = Path(".github/workflows/moteur-lawradar.yml").read_text(encoding="utf-8")
        collector = Path(".github/workflows/collect-dila-jorf.yml").read_text(encoding="utf-8")
        self.assertIn('timezone: "Europe/Paris"', motor)
        self.assertIn('cron: "9,29,49 5-16 * * *"', motor)
        self.assertIn("quiet_idle", motor)
        self.assertIn('cron: "17 17 * * *"', motor)
        self.assertIn('workflows: ["Collecte primaire DILA JORF"]', motor)
        self.assertIn("uses: ./.github/workflows/agent-presse-lawradar.yml", motor)
        self.assertIn("uses: ./.github/workflows/agent-marche-boamp-lawradar.yml", motor)
        self.assertIn("scripts/clients/entrepreneur_agent.py", motor)
        self.assertIn("evidence/client-orchestration-latest.json", motor)
        self.assertIn('cron: "17,47 5-7 * * *"', collector)
        self.assertIn('cron: "17 8 * * *"', collector)
        self.assertIn('timezone: "Europe/Paris"', collector)

    def test_refuses_more_than_the_operational_cap(self):
        items = [candidate(f"jorf:{index}", f"Texte {index}") for index in range(MAX_CANDIDATES + 1)]
        with self.assertRaisesRegex(ValueError, "limite stricte"):
            validate_motor_input(motor_input(*items))

    def test_builds_one_isolated_request_per_candidate(self):
        value = motor_input(candidate("jorf:A", "Alpha"), candidate("jorf:B", "Bêta"))
        requests, mapping = build_requests(value, "claude-sonnet-5")
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(set(mapping)), 2)
        self.assertIn("jorf:A", requests[0]["params"]["messages"][0]["content"])
        self.assertNotIn("temperature", requests[0]["params"])
        self.assertEqual(requests[0]["params"]["max_tokens"], 4096)
        self.assertNotIn("jorf:B", requests[0]["params"]["messages"][0]["content"])
        self.assertEqual(requests[0]["params"]["output_config"]["format"]["type"], "json_schema")

    def test_provider_schema_keeps_structure_but_removes_unsupported_constraints(self):
        requests, _ = build_requests(motor_input(candidate("jorf:A")), "claude-sonnet-5")
        provider_schema = requests[0]["params"]["output_config"]["format"]["schema"]
        def schema_keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(schema_keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(schema_keys(item) for item in value)) if value else set()
            return set()

        keys = schema_keys(provider_schema)
        self.assertNotIn("maxItems", keys)
        self.assertNotIn("minLength", keys)
        self.assertNotIn("minimum", keys)
        self.assertIn("required", provider_schema)
        self.assertFalse(provider_schema["additionalProperties"])
        self.assertEqual(anthropic_output_schema({"type": "array", "minItems": 1}), {"type": "array", "minItems": 1})

    def test_assembles_results_in_input_order_and_totals_usage(self):
        value = motor_input(candidate("jorf:A"), candidate("jorf:B"))
        requests, mapping = build_requests(value, "claude-sonnet-5")
        responses = [
            response(requests[1]["custom_id"], "jorf:B"),
            response(requests[0]["custom_id"], "jorf:A"),
        ]
        delivery, usage = assemble_delivery(value, responses, mapping)
        self.assertEqual([item["source_id"] for item in delivery["opportunities"]], ["jorf:A", "jorf:B"])
        self.assertEqual(usage, {"input_tokens": 200, "output_tokens": 100})

    def test_normalizes_model_signal_id_from_verified_batch_mapping(self):
        value = motor_input(candidate("jorf:A"))
        requests, mapping = build_requests(value, "claude-sonnet-5")
        item = response(requests[0]["custom_id"], "jorf:A")
        payload = json.loads(item["result"]["message"]["content"][0]["text"])
        payload["facts"]["signal_id"] = "signal:model-invented-id"
        item["result"]["message"]["content"][0]["text"] = json.dumps(payload)
        delivery, _ = assemble_delivery(value, [item], mapping)
        self.assertEqual(
            delivery["opportunities"][0]["facts"]["signal_id"], "jorf:A"
        )

    def test_completed_batch_writes_delivery_and_state(self):
        value = motor_input(candidate("jorf:A"))
        requests, _ = build_requests(value, "claude-sonnet-5")
        client = FakeClient([response(requests[0]["custom_id"], "jorf:A")])
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            output_path = Path(directory) / "delivery.json"
            state = run_batch(value, client=client, state_path=state_path, output_path=output_path, wait_seconds=0)
            self.assertTrue(state["ready"])
            self.assertTrue(output_path.exists())
            self.assertEqual(len(client.messages.batches.created), 1)
            saved_state = json.loads(state_path.read_text())
            self.assertEqual(saved_state["batch_id"], "msgbatch_test")
            self.assertIn("request_version", saved_state)

    def test_pending_batch_is_resumed_without_duplicate_submission(self):
        value = motor_input(candidate("jorf:A"))
        client = FakeClient([], starts_ended=False)
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            output_path = Path(directory) / "delivery.json"
            first = run_batch(value, client=client, state_path=state_path, output_path=output_path, wait_seconds=0)
            second = run_batch(value, client=client, state_path=state_path, output_path=output_path, wait_seconds=0)
            self.assertFalse(first["ready"])
            self.assertFalse(second["ready"])
            self.assertEqual(len(client.messages.batches.created), 1)
            self.assertEqual(client.messages.batches.retrieved, ["msgbatch_test"])
            self.assertFalse(output_path.exists())

    def test_incomplete_result_never_advances_as_a_delivery(self):
        value = motor_input(candidate("jorf:A"))
        with self.assertRaisesRegex(ValueError, "invalid_request_error"):
            assemble_delivery(
                value,
                [{"custom_id": "candidate", "result": {
                    "type": "errored",
                    "error": {"type": "error", "error": {
                        "type": "invalid_request_error", "message": "Paramètre non accepté",
                    }},
                }}],
                {"candidate": "jorf:A"},
            )

    def test_truncated_json_never_advances_and_reports_safe_diagnostics(self):
        value = motor_input(candidate("jorf:A"))
        requests, mapping = build_requests(value, "claude-sonnet-5")
        truncated = response(requests[0]["custom_id"], "jorf:A")
        truncated["result"]["message"]["content"][0]["text"] = '{"source_id":"jorf:A"'
        truncated["result"]["message"]["stop_reason"] = "max_tokens"
        truncated["result"]["message"]["usage"]["output_tokens"] = 1800
        with self.assertRaisesRegex(ValueError, "stop=max_tokens,output_tokens=1800"):
            assemble_delivery(value, [truncated], mapping)


if __name__ == "__main__":
    unittest.main()
