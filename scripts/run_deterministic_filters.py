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
ACCESS_SECTORS = {"MEDICINES", "FINANCIAL_SERVICES", "LEGAL_SERVICES", "ENERGY_EFFICIENCY", "OTHER_REGULATED", "NOT_CLASSIFIED"}
DIRECT_OFFER_STATUSES = {"ACCESSIBLE", "OUT_OF_PROFILE", "UNKNOWN", "NOT_APPLICABLE"}
PERIPHERAL_ROLE_EVIDENCE = {"VERIFIED", "PARTIAL", "MISSING", "NOT_APPLICABLE"}
PERIPHERAL_SERVICE_TYPES = {"PRESTATIONS_DE_SERVICES", "LOGICIELS", "CONSEIL", "MISE_EN_RELATION", "LOGISTIQUE"}
PERIPHERAL_SERVICE_SOURCES = {"OFFICIAL_TEXT", "BOAMP"}
SERVICE_TERMS = {
    "PRESTATIONS_DE_SERVICES": ("prestation de service", "prestations de services"),
    "LOGICIELS": ("logiciel", "logiciels", "solution logicielle"),
    "CONSEIL": ("conseil", "accompagnement"),
    "MISE_EN_RELATION": ("mise en relation", "apport d affaires", "intermediation"),
    "LOGISTIQUE": ("logistique",),
}


def result(status: str, reasons: list[str]) -> dict[str, Any]:
    return {"status": status, "reasons": reasons}


def text_key(value: str) -> str:
    """Normalise seulement ce qui est nécessaire aux règles textuelles bornées."""
    import re
    import unicodedata
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()


def valid_peripheral_service_evidence(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("service_type") not in PERIPHERAL_SERVICE_TYPES or item.get("source_kind") not in PERIPHERAL_SERVICE_SOURCES:
        return False
    if item.get("evidence_status") not in PROOF:
        return False
    if not isinstance(item.get("source_url"), str) or not item["source_url"].startswith("https://"):
        return False
    if not isinstance(item.get("excerpt"), str) or not item["excerpt"].strip():
        return False
    if not isinstance(item.get("scope_excludes_regulated_acts"), bool):
        return False
    exclusion = item.get("scope_exclusion_excerpt")
    return exclusion is None or isinstance(exclusion, str)


def service_role_candidates(access: dict[str, Any]) -> list[dict[str, Any]]:
    """Return structured candidates only; raw keywords never establish legality."""
    evidence = access.get("peripheral_service_evidence", [])
    if not isinstance(evidence, list):
        return []
    return [item for item in evidence if valid_peripheral_service_evidence(item)]


def explicitly_excludes_regulated_acts(exclusion: str) -> bool:
    """Check the minimum explicit wording required in a traced source excerpt."""
    normalized = text_key(exclusion)
    has_exclusion_marker = any(marker in normalized for marker in ("hors", "sans", "exclut", "exclusion"))
    return has_exclusion_marker and all(term in normalized for term in ("vente", "dispensation", "distribution", "medicament"))


def verified_b2b_service_role(access: dict[str, Any]) -> dict[str, Any] | None:
    """Require a source, a matching service term and an explicit exclusion.

    This is a routing rule, not legal advice or an authorization transfer.  In
    particular, generic mentions of services or logistics remain candidates.
    """
    if access.get("peripheral_role_evidence") != "VERIFIED":
        return None
    for item in service_role_candidates(access):
        excerpt = text_key(item["excerpt"])
        exclusion = text_key(item.get("scope_exclusion_excerpt") or "")
        if item["evidence_status"] != "VERIFIED" or not item["scope_excludes_regulated_acts"]:
            continue
        if not any(term in excerpt for term in SERVICE_TERMS[item["service_type"]]):
            continue
        if not explicitly_excludes_regulated_acts(exclusion):
            continue
        return item
    return None


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
    if not isinstance(facts.get("title"), str) or not facts["title"].strip():
        raise ValueError("Titre des faits invalide.")
    for key in ("keywords", "affected_scope"):
        value = facts.get(key)
        if not isinstance(value, list) or (key == "keywords" and not value) or not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError(f"{key} doit être une liste de textes exploitable.")
    legal = facts.get("legal")
    requirements = facts.get("requirements")
    if not isinstance(legal, dict) or not isinstance(requirements, dict):
        raise ValueError("Faits juridiques ou opérationnels absents.")
    if legal.get("proof_status") not in PROOF or legal.get("text_status") not in TEXT_STATUSES:
        raise ValueError("Preuve ou statut juridique invalide.")
    if not isinstance(legal.get("jurisdiction"), str) or not legal["jurisdiction"]:
        raise ValueError("Territoire juridique invalide.")
    if not isinstance(legal.get("affected_scope"), list) or not all(isinstance(item, str) and item.strip() for item in legal["affected_scope"]):
        raise ValueError("Périmètre juridique invalide.")
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
        evidence = access.get("peripheral_service_evidence", [])
        if not isinstance(evidence, list) or not all(valid_peripheral_service_evidence(item) for item in evidence):
            raise ValueError("Preuve de service périphérique invalide.")


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
    if access["sector"] == "ENERGY_EFFICIENCY" and access["direct_offer_status"] in {"ACCESSIBLE", "NOT_APPLICABLE"}:
        return {
            "status": "PASS",
            "route": "FULL_ENRICHMENT",
            "allow_external_collection": True,
            "reasons": [
                "Axe Énergie / efficacité : la collecte est limitée à la veille B2B, la qualification du besoin et la recherche de partenaires.",
                "Cette route n'autorise ni installation, ni montage de dossier CEE, ni certification, ni engagement au nom d'un obligé.",
            ],
        }
    peripheral = access["peripheral_role_evidence"]
    direct = access["direct_offer_status"]
    verified_service = verified_b2b_service_role(access)
    if direct in {"OUT_OF_PROFILE", "UNKNOWN"} and verified_service:
        return {
            "status": "PASS",
            "route": "FULL_ENRICHMENT",
            "allow_external_collection": True,
            "reasons": [
                f"Rôle B2B périphérique vérifié : {verified_service['service_type']} ({verified_service['source_kind']}).",
                "Le périmètre prouvé exclut explicitement vente, dispensation et distribution du médicament.",
            ],
        }
    candidates = service_role_candidates(access)
    if direct in {"OUT_OF_PROFILE", "UNKNOWN"} and candidates:
        return {
            "status": "HOLD",
            "route": "SERVICE_SCOPE_CHECK_ONLY",
            "allow_external_collection": False,
            "reasons": [
                "Un besoin de service B2B est identifié, mais son périmètre légal n'est pas suffisamment prouvé.",
                "Une source doit exclure explicitement vente, dispensation et distribution du médicament avant tout enrichissement.",
            ],
        }
    if direct == "OUT_OF_PROFILE":
        return {
            "status": "HOLD",
            "route": "LEGAL_ROLE_CHECK_ONLY",
            "allow_external_collection": False,
            "reasons": [
                "L'offre directe relève d'un secteur hors profil opérateur.",
                "Aucun rôle périphérique légal et accessible n'est démontré.",
            ],
        }
    if direct == "UNKNOWN":
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
