import json
import unittest

from scripts.qualify_agent_enrichment import qualify


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Messages:
    def __init__(self):
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return type("Response", (), {"content": [_Block(json.dumps({
            "schema": "lawradar-agent-enrichment-v1",
            "agent": "press",
            "signal_id": "signal:1",
            "status": "UNRESOLVED",
            "observed_at_utc": "2026-09-04T12:00:00Z",
            "summary": "Réponse de test.",
            "sources": [],
            "limitations": [],
            "details": {},
            "score": None,
        }))]})()


class _Client:
    def __init__(self):
        self.messages = _Messages()


class _EmptyMessages:
    def create(self, **_kwargs):
        return type("Response", (), {"content": []})()


class _EmptyClient:
    def __init__(self):
        self.messages = _EmptyMessages()


class QualifyAgentEnrichmentTests(unittest.TestCase):
    def test_press_uses_only_the_received_payload(self):
        client = _Client()
        payload = {"schema": "lawradar-press-qualification-input-v1", "candidates": {"candidates": []}}
        self.assertEqual(qualify(payload, "press", client=client, model="test-model")["signal_id"], "signal:1")
        self.assertEqual(client.messages.request["model"], "test-model")
        self.assertEqual(json.loads(client.messages.request["messages"][0]["content"]), payload)
        self.assertIn("ni réseau", client.messages.request["system"])
        self.assertNotIn("temperature", client.messages.request)
        self.assertEqual(client.messages.request["thinking"], {"type": "adaptive"})
        self.assertEqual(client.messages.request["output_config"], {"effort": "low"})

    def test_rejects_unknown_agent_before_any_call(self):
        with self.assertRaisesRegex(ValueError, "inconnu"):
            qualify({}, "unknown", client=_Client(), model="test-model")

    def test_empty_press_response_becomes_a_traceable_unresolved_result(self):
        payload = {
            "schema": "lawradar-press-qualification-input-v1",
            "candidates": {
                "signal_id": "signal:1", "signal_hash": "hash", "window": {}, "queries": [],
                "candidates_total": 1, "candidates_after_dedup": 1,
                "candidates": [{"url": "https://example.test/article"}],
            },
        }
        result = qualify(payload, "press", client=_EmptyClient(), model="test-model")
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["details"]["decisions"][0]["relevance"], "AMBIGUOUS")

    def test_empty_market_response_becomes_a_traceable_unresolved_result(self):
        payload = {
            "schema": "lawradar-market-qualification-input-v1",
            "observations": {
                "signal_id": "signal:1", "signal_hash": "hash", "collection_status": "COMPLETED",
                "observations": [{"url": "https://example.test/offer"}],
            },
        }
        result = qualify(payload, "market", client=_EmptyClient(), model="test-model")
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["details"]["conclusions"][0]["interpretation"], "AMBIGUOUS")
