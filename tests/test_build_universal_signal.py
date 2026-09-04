import copy
import unittest

from scripts.build_universal_signal import MAX_PRIMARY_EXCERPT_CHARS, build_dossier


def source(source_id="jorf:1"):
    return {
        "source_id": source_id,
        "source_kind": "JORF",
        "change": "NEW",
        "evidence": {"text_id": "1", "title": "Texte officiel", "interpretation": None},
        "discovery": {
            "schema": "lawradar-opportunity-discovery-v1",
            "status": "WATCH_CANDIDATE",
            "score": 4,
            "triggers": [{"kind": "LEGAL_OBLIGATION", "score": 3, "terms": ["obligation"]}],
            "scope_terms": ["entreprise"],
            "reason": "ECONOMIC_FRICTION_EVIDENCE",
            "recommended_enrichment": ["PRESS", "DEMAND", "MARKET"],
        },
    }


def facts(source_id="jorf:1"):
    return {
        "schema": "lawradar-opportunity-facts-v1", "signal_id": source_id,
        "title": "Texte officiel", "keywords": ["texte officiel"], "affected_scope": ["France"],
        "legal": {"jurisdiction": "FR", "text_status": "PUBLISHED", "proof_status": "VERIFIED", "effective_date": None, "affected_scope": ["France"]},
        "requirements": {"required_capabilities": [], "required_authorizations": [], "dependencies": [], "minimum_startup_capital_eur": None, "estimated_time_to_market_weeks": None, "evidence_status": "MISSING"},
    }


def delivery(source_id="jorf:1"):
    return {
        "schema": "lawradar-motor-delivery-v1",
        "run": {"coverage": "JORF seulement"},
        "opportunities": [{
            "source_id": source_id,
            "status": "UNRESOLVED",
            "reason": "Preuve insuffisante.",
            "facts": facts(source_id),
            "reading": {
                "consequence": "Une règle change.",
                "affected_actors": ["Entreprises"],
                "beneficiaries": ["Prestataires"],
                "constrained_parties": ["Exploitants"],
                "potential_service_partners": ["Conseils"],
                "unknowns": ["Montant"],
            },
        }],
        "money_flows": [],
    }


def motor_input(source_id="jorf:1"):
    return {
        "schema": "lawradar-motor-input-v1",
        "report_date": "2026-09-01",
        "delta_changed_sources": ["jorf-summaries-latest.json"],
        "handled_source_files": ["jorf-summaries-latest.json"],
        "rules": "inconnu = UNRESOLVED",
        "candidates": [source(source_id)],
        "excluded_historical_candidates": [],
        "excluded_routine_candidates": [],
        "excluded_no_economic_friction_candidates": [],
        "deterministically_unresolved_candidates": [],
    }


def run_manifest():
    return {"schema": "lawradar-run-manifest-v1", "run": {"id": "42", "url": "https://example.test/42", "commit": "abc"}}


class UniversalSignalTests(unittest.TestCase):
    def test_builds_a_neutral_v2_signal_without_client_slots(self):
        dossier = build_dossier(motor_input(), delivery(), run_manifest())
        self.assertEqual(dossier["schema"], "lawradar-universal-signal-v2")
        self.assertEqual(dossier["quality"]["unresolved_count"], 1)
        self.assertEqual(dossier["signals"][0]["enrichments"]["press"]["status"], "PENDING")
        self.assertIsNone(dossier["signals"][0]["enrichments"]["market"]["result"])
        self.assertNotIn("entrepreneur", dossier["signals"][0]["enrichments"])
        self.assertEqual(dossier["signals"][0]["opportunity_facts"]["signal_id"], dossier["signals"][0]["id"])
        self.assertEqual(dossier["signals"][0]["reading"]["beneficiaries"], ["Prestataires"])
        self.assertEqual(dossier["signals"][0]["reading_provenance"]["status"], "AVAILABLE")
        self.assertEqual(
            dossier["signals"][0]["reading_provenance"]["producer"],
            "MOTOR_STRUCTURED_READING",
        )
        self.assertEqual(dossier["signals"][0]["reading_provenance"]["source_id"], "jorf:1")
        self.assertEqual(dossier["signals"][0]["discovery"]["score"], 4)
        self.assertEqual(dossier["quality"]["readings_available_count"], 1)

    def test_preserves_deterministic_prefilter_exits_for_false_negative_audits(self):
        input_data = motor_input()
        input_data["excluded_routine_candidates"] = [{
            "source_id": "jorf:ROUTINE",
            "title": "Avis de vacance d'un emploi",
            "reason": "ROUTINE_PUBLIC_ADMINISTRATION_TITLE",
        }]
        input_data["deterministically_unresolved_candidates"] = [{
            "source_id": "jorf:EMPTY", "reason": "PRIMARY_TEXT_EMPTY"
        }]
        audit = build_dossier(input_data, delivery(), run_manifest())["context"]["prefilter_audit"]
        self.assertEqual(audit["excluded_routine_candidates"][0]["source_id"], "jorf:ROUTINE")
        self.assertEqual(audit["deterministically_unresolved_candidates"][0]["reason"], "PRIMARY_TEXT_EMPTY")

    def test_compacts_primary_evidence_without_its_full_text(self):
        input_data = motor_input()
        input_data["candidates"][0]["evidence"].update({
            "text_id": "JORFTEXT000000000001",
            "nature": "ARRETE",
            "nor": "TEST0001A",
            "publication_date": "2026-09-01",
            "official_url": "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000000000001",
            "archive_url": "https://dila.test/archive.tar.gz",
            "archive_sha256": "archive-sha",
            "content_status": "AVAILABLE",
            "official_text_excerpt": "A" * (MAX_PRIMARY_EXCERPT_CHARS + 500),
            "official_text_sha256": "text-sha",
            "official_detail": {
                "official_title": "Titre officiel",
                "official_period": "Du 1er au 2 septembre",
                "official_text": "Texte primaire qui ne doit pas être dupliqué.",
            },
            "financial_evidence": [
                {"source_url": "https://example.test/piece.pdf", "page": 4, "excerpt": "Extrait vérifiable"},
                {"source_url": "https://example.test/piece.pdf", "page": 4, "excerpt": "Doublon"},
            ],
        })
        compact = build_dossier(input_data, delivery(), run_manifest())["signals"][0]["source"]["evidence"]
        self.assertEqual(compact["official"]["title"], "Titre officiel")
        self.assertNotIn("official_text", compact["official"])
        self.assertEqual(compact["url"], "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000000000001")
        self.assertEqual(compact["primary_evidence"]["archive_url"], "https://dila.test/archive.tar.gz")
        self.assertEqual(compact["primary_evidence"]["text_sha256"], "text-sha")
        self.assertTrue(compact["primary_evidence"]["excerpt_truncated"])
        self.assertLessEqual(len(compact["primary_evidence"]["excerpt"]), MAX_PRIMARY_EXCERPT_CHARS)
        self.assertEqual(compact["evidence_excerpts"], [{
            "source_url": "https://example.test/piece.pdf", "page": 4, "excerpt": "Extrait vérifiable"
        }])

    def test_rejects_a_delivery_missing_a_candidate_decision(self):
        with self.assertRaises(ValueError):
            build_dossier(motor_input(), delivery("jorf:other"), run_manifest())

    def test_stable_source_identity_survives_a_later_daily_snapshot(self):
        first = build_dossier(motor_input(), delivery(), run_manifest())["signals"][0]
        later_input = copy.deepcopy(motor_input())
        later_input["report_date"] = "2026-09-02"
        later = build_dossier(later_input, delivery(), run_manifest())["signals"][0]
        self.assertNotEqual(first["id"], later["id"])
        self.assertEqual(first["identity"]["stable_source_id"], later["identity"]["stable_source_id"])
        self.assertEqual(first["identity"]["evidence_version"], later["identity"]["evidence_version"])

    def test_binds_legacy_money_flow_position_to_its_source_and_signal(self):
        current_delivery = delivery()
        current_delivery["money_flows"] = [{
            "id": "MF-01-01", "label": "Flux", "title": "Paiement",
            "money_sentence": "A paie B.", "explanation": "Preuve.",
            "payer": "A", "recipient": "B", "amount": "100 EUR",
            "effective_date": "2026-09-01", "certainty": "VERIFIED",
            "next_action": "Contrôler.",
        }]
        dossier = build_dossier(motor_input(), current_delivery, run_manifest())
        flow = dossier["money_flows"][0]
        self.assertEqual(flow["source_id"], "jorf:1")
        self.assertEqual(flow["signal_id"], dossier["signals"][0]["id"])
        self.assertEqual(flow["link_status"], "VERIFIED")
        self.assertEqual(dossier["quality"]["money_flow_unlinked_count"], 0)

    def test_marks_a_historical_delivery_without_reading_explicitly(self):
        old_delivery = delivery()
        del old_delivery["opportunities"][0]["reading"]
        signal = build_dossier(motor_input(), old_delivery, run_manifest())["signals"][0]
        self.assertIsNone(signal["reading"])
        self.assertEqual(signal["reading_provenance"]["status"], "MISSING_LEGACY")
        self.assertIsNone(signal["reading_provenance"]["basis"])
        self.assertEqual(signal["reading_provenance"]["producer"], "LEGACY_COMPATIBILITY")

    def test_recognizes_the_safe_fallback_inserted_by_an_old_batch(self):
        old_delivery = delivery()
        old_delivery["opportunities"][0]["reading"]["unknowns"] = [
            "Batch lancé avant la lecture structurée ; approfondissement à rejouer si nécessaire."
        ]
        signal = build_dossier(motor_input(), old_delivery, run_manifest())["signals"][0]
        self.assertIsNone(signal["reading"])
        self.assertEqual(signal["reading_provenance"]["status"], "MISSING_LEGACY")
        self.assertIsNone(signal["reading_provenance"]["basis"])
        self.assertEqual(signal["reading_provenance"]["producer"], "LEGACY_COMPATIBILITY")
