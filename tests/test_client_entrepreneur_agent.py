import json
import tempfile
import unittest
from pathlib import Path

from scripts.clients.entrepreneur_agent import (
    _compact_client_input,
    build_delivery,
    read_snapshot,
    run_claude_assessment,
    source_hash,
)


def dossier(with_gate=False):
    signal = {
        "id": "signal:1",
        "source": {"evidence": {"url": "https://official.test/a"}},
        "radar": {"status": "RETAINED", "reason": "Preuve officielle"},
        "discovery": {"status": "WATCH_CANDIDATE", "score": 4},
        "reading": {
            "consequence": "Une obligation crée un besoin documenté.",
            "affected_actors": ["Acheteurs"],
            "beneficiaries": ["Prestataires"],
            "constrained_parties": ["Exploitants"],
            "potential_service_partners": ["Conseils"],
            "unknowns": ["Volume exact"],
        },
        "reading_provenance": {
            "status": "AVAILABLE",
            "basis": "CANDIDATE_EVIDENCE_ONLY",
            "producer": "MOTOR_STRUCTURED_READING",
            "source_id": "jorf:1",
        },
        "enrichments": {
            "press": {"status": "COMPLETED", "result": {}},
            "demand": {"status": "COMPLETED", "result": {}},
            "market": {"status": "COMPLETED", "result": {}},
        },
    }
    if with_gate:
        signal["deterministic_filters"] = {
            "final_constraint": "PASS",
            "operator_access": {"status": "PASS", "allow_external_collection": True},
        }
        signal["opportunity_facts"] = {"estimated_market_amount_eur": 12000}
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

    def test_raw_boamp_demand_cannot_override_market_no_evidence(self):
        snapshot = dossier(with_gate=True)
        snapshot["signals"][0]["enrichments"]["market"] = {
            "status": "NO_EVIDENCE", "result": None
        }
        value = build_delivery(snapshot, "hash", "signal:1")
        self.assertEqual(value["status"], "UNRESOLVED")
        self.assertEqual(value["input_summary"]["eligible_support"], [])
        self.assertTrue(any("Marché qualifié" in item for item in value["gaps"]))

    def test_startup_capital_is_never_treated_as_a_commission_base(self):
        signal = dossier(with_gate=True)["signals"][0]
        signal["opportunity_facts"] = {
            "requirements": {"minimum_startup_capital_eur": 100000}
        }
        self.assertEqual(_compact_client_input(signal)["available_amounts_eur"], [])

    def test_client_receives_only_verified_money_flows_for_selected_signal(self):
        signal = dossier(with_gate=True)["signals"][0]
        flows = [
            {
                "signal_id": signal["id"], "link_status": "VERIFIED",
                "estimated_contract_amount_eur": 50000,
                "url": "https://example.test/linked-flow",
            },
            {
                "signal_id": "signal:other", "link_status": "VERIFIED",
                "estimated_contract_amount_eur": 90000,
            },
            {
                "signal_id": signal["id"], "link_status": "UNRESOLVED_LEGACY",
                "estimated_contract_amount_eur": 120000,
            },
        ]
        compact = _compact_client_input(signal, flows)
        self.assertEqual(compact["money_flows"], [flows[0]])
        self.assertEqual(compact["available_amounts_eur"], [12000.0, 50000.0])
        self.assertIn("https://example.test/linked-flow", compact["allowed_source_urls"])

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

    def test_closed_gate_is_skipped_without_creating_an_api_call(self):
        class ClientThatMustNotRun:
            class Messages:
                def create(self, **kwargs):
                    raise AssertionError("Claude ne doit pas être appelé")

            messages = Messages()

        snapshot = dossier(with_gate=True)
        snapshot["signals"][0]["deterministic_filters"]["final_constraint"] = "HOLD"
        result = run_claude_assessment(snapshot, "hash", "signal:1", client=ClientThatMustNotRun())
        self.assertEqual(result["status"], "SKIPPED")
        self.assertEqual(result["execution"]["external_calls"], 0)

    def test_ready_signal_uses_one_claude_call_and_validates_the_delivery(self):
        assessment = {
            "decision": "TEST",
            "axis_strategic": "Pige B2B sur un besoin public identifié.",
            "offer": {
                "service": "Qualification et mise en relation B2B",
                "target_actor": "Acheteur public",
                "provider_actor": "Prestataire spécialisé",
                "evidence_summary": "Le signal contient une assiette explicitement chiffrée.",
            },
            "commission_recommendation": {
                "rate_percent": 5,
                "base_amount_eur": 12000,
                "estimated_success_fee_eur": 600,
                "conditions": "Sous réserve d'un contrat d'apporteur d'affaires conforme.",
            },
            "first_step_protocol": {
                "hypothesis": "Un prestataire est prêt à répondre à ce besoin.",
                "draft_action": "Préparer une liste courte de prestataires, sans contact.",
                "success_signal": "Trois prestataires qualifiables sont identifiés.",
                "stop_condition": "Aucun prestataire vérifiable n'est trouvé.",
                "max_duration_days": 3,
            },
            "source_urls": ["https://official.test/a"],
        }

        class FakeMessages:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "id": "msg_test",
                    "usage": {"input_tokens": 101, "output_tokens": 202},
                    "content": [{"type": "text", "text": json.dumps(assessment)}],
                }

        class FakeClient:
            def __init__(self):
                self.messages = FakeMessages()

        client = FakeClient()
        result = run_claude_assessment(dossier(with_gate=True), "hash", "signal:1", client=client)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["business_assessment"]["decision"], "TEST")
        self.assertEqual(result["execution"]["external_calls"], 1)
        self.assertFalse(result["execution"]["writes_to_core"])
        self.assertEqual(client.messages.calls[0]["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(client.messages.calls[0]["output_config"]["effort"], "medium")
        self.assertEqual(client.messages.calls[0]["thinking"], {"type": "adaptive"})
        prompt = json.loads(client.messages.calls[0]["messages"][0]["content"])
        self.assertEqual(prompt["reading"], dossier(with_gate=True)["signals"][0]["reading"])
        self.assertEqual(prompt["reading_provenance"]["status"], "AVAILABLE")
        self.assertEqual(prompt["discovery"]["score"], 4)
