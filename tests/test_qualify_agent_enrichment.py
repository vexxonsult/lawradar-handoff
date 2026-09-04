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
        return type("Response", (), {"content": [_Block(json.dumps({"ok": True}))]})()


class _Client:
    def __init__(self):
        self.messages = _Messages()


class QualifyAgentEnrichmentTests(unittest.TestCase):
    def test_press_uses_only_the_received_payload(self):
        client = _Client()
        payload = {"schema": "lawradar-press-qualification-input-v1", "candidates": {"candidates": []}}
        self.assertEqual(qualify(payload, "press", client=client, model="test-model"), {"ok": True})
        self.assertEqual(client.messages.request["model"], "test-model")
        self.assertEqual(json.loads(client.messages.request["messages"][0]["content"]), payload)
        self.assertIn("ni réseau", client.messages.request["system"])

    def test_rejects_unknown_agent_before_any_call(self):
        with self.assertRaisesRegex(ValueError, "inconnu"):
            qualify({}, "unknown", client=_Client(), model="test-model")

