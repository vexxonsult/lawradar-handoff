import unittest

from scripts.render_dashboard import render_dashboard, validate_result


class RenderDashboardTests(unittest.TestCase):
    def result(self):
        return {
            "schema": "lawradar-dashboard-input-v1",
            "report_date": "2026-08-31", "headline": "Un changement suivi",
            "coverage": "Couverture vérifiée",
            "flows": [{
                "label": "Dépense potentielle", "title": "Titre <sûr>",
                "money_sentence": "Une dépense pourrait apparaître.",
                "explanation": "Explication.", "payer": "Entreprises",
                "recipient": "Prestataires", "amount": "À déterminer",
                "effective_date": "1er janvier 2027", "certainty": "Rapporté",
                "next_action": "Lire le texte primaire.",
            }],
            "readings": [{
                "title": "Titre <sûr>", "status": "DISCARDED", "reason": "Contexte lu.",
                "reading": {
                    "consequence": "Une conséquence factuelle.", "affected_actors": ["Acteur"],
                    "beneficiaries": [], "constrained_parties": [],
                    "potential_service_partners": [], "unknowns": ["Montant non démontré."],
                },
            }],
        }

    def test_renders_user_level_card_and_escapes_content(self):
        page = render_dashboard(self.result())
        self.assertIn("Dépense potentielle", page)
        self.assertIn("Une dépense pourrait apparaître.", page)
        self.assertIn("Titre &lt;sûr&gt;", page)
        self.assertNotIn("<sûr>", page)
        self.assertIn("Lecture de tous les textes", page)

    def test_rejects_incomplete_motor_result(self):
        result = self.result()
        del result["flows"][0]["payer"]
        with self.assertRaises(ValueError):
            validate_result(result)
