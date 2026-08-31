import unittest

from scripts.render_motor_delivery import dashboard_input, validate_delivery


class MotorDeliveryTests(unittest.TestCase):
    def delivery(self):
        return {
            "schema": "lawradar-motor-delivery-v1",
            "run": {"report_date": "2026-08-31", "coverage": "COUVERTURE OK", "summary": "Un flux testé"},
            "opportunities": [{"source_id": "JORFTEXT1", "status": "RETAINED", "reason": "Preuve suffisante"}],
            "money_flows": [{
                "id": "MF-1", "label": "Flux", "title": "Titre", "money_sentence": "P vers R",
                "explanation": "Explication", "payer": "P", "recipient": "R", "amount": "Non chiffré",
                "effective_date": "2027", "certainty": "À confirmer", "next_action": "Lire la preuve"
            }],
        }

    def test_dashboard_mapping(self):
        result = dashboard_input(self.delivery())
        self.assertEqual(result["headline"], "Un flux testé")
        self.assertEqual(result["flows"][0]["payer"], "P")

    def test_rejects_duplicate_flow_id(self):
        payload = self.delivery()
        payload["money_flows"].append(payload["money_flows"][0].copy())
        with self.assertRaises(ValueError):
            validate_delivery(payload)
