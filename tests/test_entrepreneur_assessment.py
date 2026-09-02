import copy
import unittest

from scripts.prepare_entrepreneur_input import build
from scripts.validate_entrepreneur_assessment import validate


def result(agent, url):
    return {
        "schema": "lawradar-agent-enrichment-v1", "agent": agent, "signal_id": "signal:1",
        "status": "COMPLETED", "observed_at_utc": "2026-09-02T12:00:00Z", "summary": "Constat sourcé. [1]",
        "sources": [{"url": url, "title": "Source"}], "limitations": [], "details": {}, "score": None,
    }


def dossier(statuses=None):
    statuses = statuses or {"press": "COMPLETED", "demand": "COMPLETED", "market": "NO_EVIDENCE"}
    urls = {"press": "https://press.test/a", "demand": "https://demand.test/a", "market": "https://market.test/a"}
    enrichments = {}
    for agent, status in statuses.items():
        enrichments[agent] = {"status": status, "result": result(agent, urls[agent]) if status == "COMPLETED" else None}
    return {
        "schema": "lawradar-universal-signal-v1",
        "signals": [{
            "id": "signal:1", "source": {"evidence": {"url": "https://official.test/a"}},
            "radar": {"status": "RETAINED", "reason": "Preuve officielle"}, "enrichments": enrichments,
        }], "money_flows": [],
    }


def assessment(input_data, status="COMPLETED", decision="TEST"):
    return {
        "schema": "lawradar-agent-enrichment-v1", "agent": "entrepreneur", "signal_id": "signal:1", "status": status,
        "observed_at_utc": "2026-09-02T12:01:00Z", "summary": "Une décision exploratoire est justifiée. [1]",
        "sources": [{"url": "https://demand.test/a", "title": "Source Demande"}], "limitations": [],
        "details": {
            "signal_hash": input_data["signal_hash"],
            "support_statuses": {agent: input_data["support"][agent]["status"] for agent in ("press", "demand", "market")},
            "decision": decision, "gaps": [],
            "test_protocol": {"hypothesis": "L'intérêt mesuré mérite une vérification.", "method": "Entretien exploratoire sans engagement.", "success_signal": "Besoin confirmé par des réponses explicites.", "stop_condition": "Aucune réponse pertinente.", "max_duration_days": 14},
        }, "score": None,
    }


class EntrepreneurAssessmentTests(unittest.TestCase):
    def test_prepares_only_the_current_signal_and_support_outputs(self):
        value = build(dossier(), "signal:1")
        self.assertEqual(value["schema"], "lawradar-entrepreneur-input-v1")
        self.assertIn("https://official.test/a", value["allowed_source_urls"])
        self.assertNotIn("Sibelco", str(value))

    def test_accepts_a_reversible_test_after_terminal_support(self):
        input_data = build(dossier(), "signal:1")
        validate(input_data, assessment(input_data))

    def test_rejects_a_test_when_a_support_agent_is_pending(self):
        input_data = build(dossier({"press": "COMPLETED", "demand": "PENDING", "market": "NO_EVIDENCE"}), "signal:1")
        invalid = assessment(input_data)
        with self.assertRaises(ValueError):
            validate(input_data, invalid)

    def test_accepts_investigate_when_a_support_agent_is_pending(self):
        input_data = build(dossier({"press": "COMPLETED", "demand": "PENDING", "market": "NO_EVIDENCE"}), "signal:1")
        valid = assessment(input_data, status="UNRESOLVED", decision="INVESTIGATE")
        valid["sources"] = []
        valid["summary"] = "La décision doit attendre la mesure de demande."
        valid["details"]["gaps"] = ["Mesure Demande absente."]
        valid["details"]["test_protocol"] = None
        validate(input_data, valid)

    def test_rejects_an_invented_source(self):
        input_data = build(dossier(), "signal:1")
        invalid = copy.deepcopy(assessment(input_data))
        invalid["sources"][0]["url"] = "https://invented.test/a"
        with self.assertRaises(ValueError):
            validate(input_data, invalid)
