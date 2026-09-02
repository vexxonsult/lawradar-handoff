#!/usr/bin/env python3
"""Évalue conformité et faisabilité sans IA ni appel réseau."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


PROOF = {"VERIFIED", "PARTIAL", "MISSING"}
TEXT_STATUSES = {"PUBLISHED", "IN_FORCE", "CONSULTATION_OPEN", "DRAFT", "REPEALED", "EXPIRED", "UNKNOWN"}
AUTH_STATUSES = {"REQUIRED", "NOT_REQUIRED", "UNKNOWN", "UNAVAILABLE"}
DEPENDENCY_STATUSES = {"AVAILABLE", "UNKNOWN", "BLOCKING"}
ACCESS_SECTORS = {"MEDICINES", "FINANCIAL_SERVICES", "LEGAL_SERVICES", "OTHER_REGULATED", "NOT_CLASSIFIED"}
DIRECT_OFFER_STATUSES = {"ACCESSIBLE", "OUT_OF_PROFILE", "UNKNOWN", "NOT_APPLICABLE"}
PERIPHERAL_ROLE_EVIDENCE = {"VERIFIED", "PARTIAL", "MISSING", "NOT_APPLICABLE"}


def result(status: str, reasons: list[str]) -> dict[str, Any]:
    return {"status": status, "reasons": reasons}


def parse_date(value: Any, label: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} invalide.")
    try:
        return date.fromisoformat(value)
    except ValueError as caught:
        raise ValueError(f"{label} invalide.") from caught


def validate_facts(facts: dict[str, Any]) -> None:
    if facts.get("schema") != "lawradar-opportunity-facts-v1":
        raise ValueError("Faits d'opportunité non pris en charge.")
    if not isinstance(facts.get("signal_id"), str) or not facts["signal_id"]:
        raise ValueError("Signal des faits invalide.")
    legal = facts.get("legal")
    requirements = facts.get("requirements")
    if not isinstance(legal, dict) or not isinstance(requirements, dict):
        raise ValueError("Faits juridiques ou opérationnels absents.")
    if legal.get("proof_status") not in PROOF or legal.get("text_status") not in TEXT_STATUSES:
        raise ValueError("Preuve ou statut juridique invalide.")
    if requirements.get("evidence_status") not in PROOF:
        raise ValueError("Statut de preuve opérationnelle invalide.")
    for key in ("required_capabilities", "required_authorizations", "dependencies"):
        if not isinstance(requirements.get(key), list):
            raise ValueError(f"{key} doit être une liste.")
    for item in requirements["required_authorizations"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item.get("status") not in AUTH_STATUSES:
            raise ValueError("Autorisation requise invalide.")
    for item in requirements["dependencies"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item.get("status") not in DEPENDENCY_STATUSES:
            raise ValueError("Dépendance invalide.")
    for key in ("minimum_startup_capital_eur", "estimated_time_to_market_weeks"):
        value = requirements.get(key)
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            raise ValueError(f"{key} invalide.")
    access = facts.get("operator_access")
    if access is not None:
        if not isinstance(access, dict):
            raise ValueError("Routage opérateur invalide.")
        if access.get("sector") not in ACCESS_SECTORS:
            raise ValueError("Secteur de routage opérateur invalide.")
        if access.get("direct_offer_status") not in DIRECT_OFFER_STATUSES:
            raise ValueError("Statut d'offre directe invalide.")
        if access.get("peripheral_role_evidence") not in PERIPHERAL_ROLE_EVIDENCE:
            raise ValueError("Preuve de rôle périphérique invalide.")
        if access.get("evidence_status") not in PROOF:
            raise ValueError("Preuve de routage opérateur invalide.")


def compliance_filter(facts: dict[str, Any], policy: dict[str, Any], today: date) -> dict[str, Any]:
    legal = facts["legal"]
    if legal["proof_status"] != "VERIFIED":
        return result("INVESTIGATE", ["Preuve juridique incomplète ou absente."])
    if legal.get("jurisdiction") not in policy["accepted_jurisdictions"]:
        return result("DISCARD", ["Territoire hors périmètre opérateur."])
    status = legal["text_status"]
    if status in {"REPEALED", "EXPIRED"}:
        return result("DISCARD", ["Texte abrogé ou expiré."])
    if status in policy["watch_text_statuses"]:
        return result("WATCH", ["Texte encore en consultation ou projet."])
    if status not in policy["actionable_text_statuses"]:
        return result("INVESTIGATE", ["Statut juridique non exploitable."])
    effective = parse_date(legal.get("effective_date"), "Date d'effet")
    if effective is None:
        return result("INVESTIGATE", ["Date d'effet inconnue."])
    if effective > today + timedelta(days=int(policy["maximum_effective_delay_days"])):
        return result("WATCH", ["Entrée en vigueur trop lointaine pour une action immédiate."])
    return result("PASS", ["Texte vérifié, dans le périmètre et actionnable."])


def feasibility_filter(facts: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    requirements = facts["requirements"]
    blockers: list[str] = []
    unknown: list[str] = []
    if requirements["evidence_status"] != "VERIFIED":
        unknown.append("Preuve opérationnelle incomplète ou absente.")
    available_capabilities = set(profile["available_capabilities"])
    for capability in requirements["required_capabilities"]:
        if not isinstance(capability, str) or not capability:
            unknown.append("Compétence requise non identifiée.")
        elif capability not in available_capabilities:
            blockers.append(f"Compétence indispensable absente : {capability}.")
    available_authorizations = set(profile.get("available_authorizations", []))
    for authorization in requirements["required_authorizations"]:
        if authorization["status"] == "UNAVAILABLE":
            blockers.append(f"Autorisation indisponible : {authorization['id']}.")
        elif authorization["status"] == "UNKNOWN":
            unknown.append(f"Statut de l'autorisation inconnu : {authorization['id']}.")
        elif authorization["status"] == "REQUIRED" and authorization["id"] not in available_authorizations:
            blockers.append(f"Autorisation requise absente : {authorization['id']}.")
    for dependency in requirements["dependencies"]:
        if dependency["status"] == "BLOCKING":
            blockers.append(f"Dépendance bloquante : {dependency['id']}.")
        elif dependency["status"] == "UNKNOWN":
            unknown.append(f"Dépendance non vérifiée : {dependency['id']}.")
    capital = requirements["minimum_startup_capital_eur"]
    if capital is None:
        unknown.append("Capital de départ inconnu.")
    elif capital > profile["max_startup_capital_eur"]:
        blockers.append("Capital de départ supérieur au plafond opérateur.")
    ttm = requirements["estimated_time_to_market_weeks"]
    if ttm is None:
        unknown.append("Délai de mise sur le marché inconnu.")
    elif ttm > profile["max_time_to_market_weeks"]:
        blockers.append("Délai de mise sur le marché supérieur au plafond opérateur.")
    if blockers:
        return result("DISCARD", blockers)
    if unknown:
        return result("INVESTIGATE", unknown)
    return result("PASS", ["Compatible avec le profil de ressources versionné."])


def operator_access_filter(facts: dict[str, Any]) -> dict[str, Any]:
    """Route a regulated direct offer before costly enrichment agents run.

    This does not decide whether a regulated market is legal or attractive. It
    only stops a small operator profile from treating a medicine, financial or
    legal signal as an immediately actionable direct-sale opportunity without a
    documented, lawful peripheral role.
    """
    access = facts.get("operator_access")
    if access is None or access["sector"] == "NOT_CLASSIFIED":
        return {
            "status": "NOT_APPLICABLE",
            "route": "FULL_ENRICHMENT",
            "allow_external_collection": True,
            "reasons": ["Aucun secteur fortement réglementé n'est déclaré dans les faits."],
        }
    peripheral = access["peripheral_role_evidence"]
    direct = access["direct_offer_status"]
    if direct == "OUT_OF_PROFILE" and peripheral != "VERIFIED":
        return {
            "status": "HOLD",
            "route": "LEGAL_ROLE_CHECK_ONLY",
            "allow_external_collection": False,
            "reasons": [
                "L'offre directe relève d'un secteur hors profil opérateur.",
                "Aucun rôle périphérique légal et accessible n'est démontré.",
            ],
        }
    if direct == "UNKNOWN" and peripheral != "VERIFIED":
        return {
            "status": "HOLD",
            "route": "LEGAL_ROLE_CHECK_ONLY",
            "allow_external_collection": False,
            "reasons": [
                "L'accessibilité d'une offre directe n'est pas établie.",
                "Aucun rôle périphérique légal et accessible n'est démontré.",
            ],
        }
    return {
        "status": "PASS",
        "route": "FULL_ENRICHMENT",
        "allow_external_collection": True,
        "reasons": ["Un rôle opérateur accessible est documenté pour ce signal."],
    }


def final_constraint(compliance: str, feasibility: str, operator_access: str) -> str:
    if "DISCARD" in {compliance, feasibility}:
        return "DISCARD"
    if "INVESTIGATE" in {compliance, feasibility} or operator_access == "HOLD":
        return "INVESTIGATE"
    if "WATCH" in {compliance, feasibility}:
        return "WATCH"
    return "PASS"


def evaluate(facts: dict[str, Any], policy: dict[str, Any], profile: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    validate_facts(facts)
    if policy.get("schema") != "lawradar-compliance-policy-v1" or profile.get("schema") != "lawradar-operator-profile-v1":
        raise ValueError("Politique de conformité ou profil opérateur non pris en charge.")
    current = now or datetime.now(UTC)
    compliance = compliance_filter(facts, policy, current.date())
    feasibility = feasibility_filter(facts, profile)
    access = operator_access_filter(facts)
    return {
        "schema": "lawradar-deterministic-filters-v1",
        "signal_id": facts["signal_id"],
        "evaluated_at_utc": current.isoformat(),
        "compliance": compliance,
        "feasibility": feasibility,
        "operator_access": access,
        "final_constraint": final_constraint(compliance["status"], feasibility["status"], access["status"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.facts.read_text(encoding="utf-8")),
        json.loads(args.policy.read_text(encoding="utf-8")),
        json.loads(args.profile.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
