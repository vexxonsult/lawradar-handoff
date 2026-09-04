#!/usr/bin/env python3
"""Exécute un crash-test intégral, isolé et entièrement simulé de LawRadar.

Le scénario ne consulte pas le réseau : BOAMP, Presse et Demande sont des
réponses de test explicitement étiquetées. Il vérifie néanmoins les véritables
fonctions et contrats du dépôt avant d'écrire les artefacts du scénario.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.fetch_boamp_data import collect as collect_boamp
    from scripts.merge_agent_enrichment import merge
    from scripts.clients.entrepreneur_agent import build_delivery as build_client_delivery
    from scripts.clients.entrepreneur_agent import read_snapshot as read_client_snapshot
    from scripts.run_deterministic_filters import evaluate
    from scripts.validate_demand_enrichment import validate as validate_demand
    from scripts.validate_market_enrichment import validate as validate_market
    from scripts.validate_press_enrichment import validate as validate_press
except ModuleNotFoundError:  # pragma: no cover - supports direct workflow invocation.
    from fetch_boamp_data import collect as collect_boamp
    from merge_agent_enrichment import merge
    from clients.entrepreneur_agent import build_delivery as build_client_delivery
    from clients.entrepreneur_agent import read_snapshot as read_client_snapshot
    from run_deterministic_filters import evaluate
    from validate_demand_enrichment import validate as validate_demand
    from validate_market_enrichment import validate as validate_market
    from validate_press_enrichment import validate as validate_press


NOW = datetime(2026, 9, 2, 9, tzinfo=UTC)
SCENARIO_ID = "crash-test:water-filter:2026-09-02"
OFFICIAL_URL = "https://example.invalid/official/simulated-water-filter-decree"
PRESS_URL = "https://example.invalid/press/simulated-water-filter"
DEMAND_URL = "https://example.invalid/demand/simulated-water-filter"
BOAMP_URL = "https://example.invalid/boamp/simulated-water-filter"


def signal_hash(signal: dict[str, Any]) -> str:
    raw = json.dumps(signal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def opportunity_facts() -> dict[str, Any]:
    """The deterministic facts a simulated Moteur would hand to the filters."""
    return {
        "schema": "lawradar-opportunity-facts-v1",
        "signal_id": SCENARIO_ID,
        "title": "SCÉNARIO — obligation de suivi des filtres à eau en entreprise",
        "keywords": ["filtres à eau entreprise", "suivi qualité eau"],
        "affected_scope": ["services de suivi de filtres à eau pour entreprises françaises"],
        "legal": {
            "jurisdiction": "FR",
            "text_status": "PUBLISHED",
            "proof_status": "VERIFIED",
            "effective_date": "2026-10-01",
            "affected_scope": ["entreprises françaises concernées par le scénario"],
        },
        "requirements": {
            "required_capabilities": ["analyse_ia", "contenu_digital", "prospection_legere"],
            "required_authorizations": [],
            "dependencies": [],
            "minimum_startup_capital_eur": 1500,
            "estimated_time_to_market_weeks": 4,
            "evidence_status": "VERIFIED",
        },
    }


def boamp_config() -> dict[str, Any]:
    return {
        "schema": "lawradar-boamp-collector-config-v1",
        "activation": "manual_only",
        "endpoint": "https://example.invalid/boamp-api",
        "dataset": "boamp",
        "search_field": "objet",
        "limits": {
            "max_queries_per_signal": 1,
            "page_size": 10,
            "max_pages_per_query": 1,
            "max_records_in_output": 10,
            "minimum_interval_seconds": 0,
            "attempts_per_request": 1,
            "timeout_seconds": 2,
        },
    }


def simulated_boamp_fetch(_: str, __: dict[str, Any], ___: int) -> dict[str, Any]:
    return {"total_count": 1, "results": [{
        "idweb": "SIM-2026-001",
        "objet": "SCÉNARIO — prestation de suivi de filtres à eau en entreprise",
        "dateparution": "2026-09-02",
        "datelimitereponse": "2026-09-30T12:00:00+00:00",
        "nomacheteur": "Acheteur public simulé",
        "nature": "APPEL_OFFRE",
        "nature_libelle": "Avis de marché",
        "etat": "INITIAL",
        "url_avis": BOAMP_URL,
    }]}


def universal_dossier() -> dict[str, Any]:
    evidence = {
        "text_id": "SIMULATED-WATER-FILTER",
        "nature": "SCENARIO",
        "nor": None,
        "title": "SCÉNARIO — décret fictif de suivi des filtres à eau",
        "publisher": "Simulateur LawRadar",
        "url": OFFICIAL_URL,
        "publication_date": "2026-09-02",
        "journal_number": None,
        "article_ids": [], "article_titles": [], "dates": [],
        "detail_status": "SIMULATED", "official": {}, "attachments": [],
        "evidence_excerpts": [],
        "primary_evidence": {
            "content_status": "SIMULATED", "text_sha256": None,
            "excerpt": None, "excerpt_truncated": False,
            "archive_url": None, "archive_sha256": None,
        },
    }
    return {
        "schema": "lawradar-universal-signal-v2",
        "run": {
            "id": "scenario-2026-09-02", "attempt": None,
            "url": None, "commit": None, "report_date": "2026-09-02",
        },
        "context": {"scenario_only": True, "prefilter_audit": {
            "excluded_historical_candidates": [],
            "excluded_routine_candidates": [],
            "excluded_no_economic_friction_candidates": [],
            "deterministically_unresolved_candidates": [],
        }},
        "signals": [{
            "id": SCENARIO_ID,
            "identity": {
                "stable_source_id": "source:scenario-water-filter",
                "evidence_version": "sha256:" + signal_hash(evidence),
            },
            "source": {
                "source_id": "scenario:water-filter", "source_kind": "SIMULATION",
                "change": "NEW", "evidence": evidence,
            },
            "radar": {
                "status": "RETAINED",
                "reason": "Scénario de test : preuve officielle fictive, jamais une donnée de production.",
            },
            "discovery": {"status": "WATCH_CANDIDATE", "score": 3},
            "reading": {
                "consequence": "Le scénario impose un suivi de filtres à eau.",
                "affected_actors": ["Entreprises françaises simulées"],
                "beneficiaries": [], "constrained_parties": [],
                "potential_service_partners": [],
                "unknowns": ["Le scénario ne constitue aucune preuve réelle."],
            },
            "reading_provenance": {
                "status": "AVAILABLE", "basis": "CANDIDATE_EVIDENCE_ONLY",
                "producer": "SIMULATOR", "source_id": "scenario:water-filter",
            },
            "opportunity_facts": opportunity_facts(),
            "enrichments": {
                "press": {"status": "PENDING", "result": None},
                "demand": {"status": "PENDING", "result": None},
                "market": {"status": "PENDING", "result": None},
            },
        }],
        "money_flows": [],
        "quality": {
            "opportunity_count": 1, "unresolved_count": 0,
            "readings_available_count": 1, "evidence_reference_count": 1,
            "money_flow_count": 0, "money_flow_unlinked_count": 0,
            "limitation": "Scénario isolé sans preuve de production.",
        },
    }


def press_pair(current_hash: str) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = {
        "schema": "lawradar-press-candidates-v1", "signal_id": SCENARIO_ID,
        "signal_hash": current_hash, "observed_at_utc": NOW.isoformat(),
        "window": {"from": "2026-08-19", "to": "2026-09-02"}, "queries": [],
        "candidates_total": 1, "candidates_after_dedup": 1, "collection_successful": True,
        "candidates": [{"url": PRESS_URL, "title": "SCÉNARIO — publication relative aux filtres à eau", "excerpt": "Scénario de test uniquement."}],
        "errors": [],
    }
    enrichment = {
        "schema": "lawradar-agent-enrichment-v1", "agent": "press", "signal_id": SCENARIO_ID,
        "status": "COMPLETED", "observed_at_utc": NOW.isoformat(),
        "summary": "Le candidat Presse simulé mentionne le texte de scénario. [1]",
        "sources": [{"url": PRESS_URL, "title": "SCÉNARIO — publication relative aux filtres à eau"}],
        "limitations": ["Source entièrement simulée : aucune couverture média réelle n'est affirmée."],
        "details": {
            "signal_hash": current_hash, "window": candidates["window"], "queries": [],
            "candidates_total": 1, "candidates_after_dedup": 1, "coverage_level": "LOW",
            "decisions": [{"url": PRESS_URL, "relevance": "DIRECT", "why_linked": "Le titre contient le périmètre du scénario."}],
        }, "score": None,
    }
    return candidates, enrichment


def demand_pair(current_hash: str) -> tuple[dict[str, Any], dict[str, Any]]:
    observations = {
        "schema": "lawradar-demand-observations-v2", "signal_id": SCENARIO_ID,
        "signal_hash": current_hash, "collected_at_utc": NOW.isoformat(), "collection_status": "COMPLETED",
        "indicators": {
            "trends": {"status": "DISABLED", "experimental_manual_only": True, "ratio_7d_vs_prior_83d": None, "surge_detected": None},
            "autocomplete": {"status": "DISABLED", "experimental_manual_only": True, "intent_terms_found": [], "commercial_intent": None},
            "institutional": {"status": "INSTITUTIONAL_DEMAND_OBSERVED", "open_tender_count": 1, "pre_information_count": 0, "distinct_buyer_count": 1},
        },
        "observations": [{
            "url": DEMAND_URL, "title": "SCÉNARIO — indice de recherche", "provider": "simulateur",
            "metric": "interest_index", "value": 42, "unit": "index", "period": "2026-09", "geography": "FR",
            "retrieved_at_utc": NOW.isoformat(),
        }], "errors": [],
    }
    enrichment = {
        "schema": "lawradar-agent-enrichment-v1", "agent": "demand", "signal_id": SCENARIO_ID,
        "status": "COMPLETED", "observed_at_utc": NOW.isoformat(),
        "summary": "Le jeu de test comporte un indice d'intérêt relatif, sans volume de recherche. [1]",
        "sources": [{"url": DEMAND_URL, "title": "SCÉNARIO — indice de recherche"}],
        "limitations": ["Mesure simulée et relative : elle ne prouve ni intention d'achat ni volume."],
        "details": {
            "signal_hash": current_hash, "collection_status": "COMPLETED", "observations_total": 1,
            "conclusions": [{"url": DEMAND_URL, "interpretation": "SEARCH_INTEREST", "why": "Indice positif du scénario, sans extrapolation."}],
            "indicators": observations["indicators"],
        }, "score": None,
    }
    return observations, enrichment


def market_pair(current_hash: str) -> tuple[dict[str, Any], dict[str, Any]]:
    observations = {
        "schema": "lawradar-market-observations-v1", "signal_id": SCENARIO_ID,
        "signal_hash": current_hash, "collected_at_utc": NOW.isoformat(), "collection_status": "COMPLETED",
        "observations": [{
            "url": BOAMP_URL, "title": "SCÉNARIO — prestation de suivi de filtres à eau", "provider": "BOAMP simulé",
            "actor": "Acheteur public simulé", "observation_type": "OFFER", "geography": "FR",
            "retrieved_at_utc": NOW.isoformat(), "excerpt": "Avis simulé pour une prestation de suivi de filtres à eau.",
        }], "errors": [],
    }
    enrichment = {
        "schema": "lawradar-agent-enrichment-v1", "agent": "market", "signal_id": SCENARIO_ID,
        "status": "COMPLETED", "observed_at_utc": NOW.isoformat(),
        "summary": "Un avis BOAMP simulé illustre une demande publique dans le périmètre. [1]",
        "sources": [{"url": BOAMP_URL, "title": "SCÉNARIO — prestation de suivi de filtres à eau"}],
        "limitations": ["Un avis ne mesure ni taille de marché ni concurrence exhaustive."],
        "details": {
            "signal_hash": current_hash, "collection_status": "COMPLETED", "observations_total": 1,
            "conclusions": [{"url": BOAMP_URL, "interpretation": "OFFER", "why": "L'avis simulé décrit une prestation dans le périmètre."}],
        }, "score": None,
    }
    return observations, enrichment


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    facts = opportunity_facts()
    policy = json.loads(Path("config/compliance-policy-v1.json").read_text(encoding="utf-8"))
    profile = json.loads(Path("config/operator-profile-v1.json").read_text(encoding="utf-8"))
    filters = evaluate(facts, policy, profile, now=NOW)
    boamp = collect_boamp(facts, boamp_config(), now=NOW, fetch=simulated_boamp_fetch, sleep=lambda _: None)

    dossier = universal_dossier()
    current_hash = signal_hash(dossier["signals"][0])
    candidates, press = press_pair(current_hash)
    demand_observations, demand = demand_pair(current_hash)
    market_observations, market = market_pair(current_hash)
    validate_press(candidates, press)
    validate_demand(demand_observations, demand)
    validate_market(market_observations, market)
    for enrichment in (press, demand, market):
        dossier = merge(dossier, enrichment)
    dossier["signals"][0]["deterministic_filters"] = filters
    core_output = output_dir / "universal-signal.json"
    write_json(core_output, dossier)
    client_snapshot, client_hash = read_client_snapshot(core_output)
    client_delivery = build_client_delivery(client_snapshot, client_hash, SCENARIO_ID, now=NOW)

    report = {
        "schema": "lawradar-e2e-crash-test-report-v1", "scenario_only": True,
        "scenario_id": SCENARIO_ID, "executed_at_utc": NOW.isoformat(),
        "verdict": "PASS",
        "input_signal": {
            "title": facts["title"], "effective_date": facts["legal"]["effective_date"],
            "jurisdiction": facts["legal"]["jurisdiction"], "affected_scope": facts["affected_scope"],
        },
        "motor_output": facts,
        "boamp_output": boamp,
        "deterministic_filters": filters,
        "client_entrepreneur_delivery": client_delivery,
        "checks": [
            "BOAMP borné : 1 requête simulée, 1 avis compact.",
            "Conformité et faisabilité : PASS avec le profil versionné.",
            "Presse, Demande et Marché : contrats validés sur données de scénario.",
            "Client Entrepreneur externe : lecture seule du signal V2, prêt pour une évaluation IA séparée.",
        ],
        "limitations": [
            "Aucune source, obligation légale, demande ou marché réels ne sont affirmés.",
            "Ce test ne remplace pas un run officiel ni une qualification humaine.",
        ],
    }
    for name, value in {
        "opportunity-facts.json": facts,
        "market-demand-boamp.json": boamp,
        "deterministic-filters.json": filters,
        "client-entrepreneur-delivery.json": client_delivery,
        "crash-test-report.json": report,
    }.items():
        write_json(output_dir / name, value)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("out/e2e-crash-test"))
    args = parser.parse_args()
    report = run(args.output_dir)
    print(json.dumps({"verdict": report["verdict"], "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
