#!/usr/bin/env python3
"""Détecte sobrement les frictions économiques dans une preuve officielle.

Cette couche ne décide jamais qu'une opportunité existe. Elle sert uniquement à
sélectionner les textes qui justifient une enquête factuelle ultérieure : une
obligation, une échéance, une aide, une exigence d'accès, un achat public ou une
transition technique peuvent créer une friction pour des organisations. Les
filtres aval et les clients restent seuls habilités à conclure sur une offre.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


SCHEMA = "lawradar-opportunity-discovery-v1"
MINIMUM_WATCH_SCORE = 3


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


# The wording is intentionally broad enough to span sectors, while the score
# threshold prevents a simple effective-date notice from consuming a model call.
TRIGGER_RULES: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("LEGAL_OBLIGATION", 3, (
        "obligation", "obligatoire", "doivent", "doit ", "est tenu de",
        "mise en conformite", "interdiction", "soumis a",
    )),
    ("SANCTION_OR_CONTROL", 3, (
        "sanction", "amende", "penalite", "controle", "manquement",
    )),
    ("FUNDING_OR_INCENTIVE", 3, (
        "subvention", "aide ", "bonification", "certificat d'economies",
        "financement", "fonds", "credit d'impot", "tarif",
    )),
    ("PUBLIC_PURCHASE_OR_COLLECTIVITY", 3, (
        "marche public", "appel d'offres", "acheteur public", "collectivites",
        "etablissement public", "commande publique",
    )),
    ("ELIGIBILITY_OR_CERTIFICATION", 2, (
        "agrement", "certification", "habilitation", "homologation",
        "referentiel", "eligibilite", "liste des produits",
    )),
    ("REPORTING_OR_TRACEABILITY", 2, (
        "registre", "declaration", "reporting", "tracabilite", "transmission",
        "teledeclaration",
    )),
    ("TECHNICAL_TRANSITION", 2, (
        "efficacite energetique", "economies d'energie", "chaudiere",
        "recyclage", "decarbonation", "transition energetique",
    )),
    ("DEADLINE_OR_ENTRY_INTO_FORCE", 1, (
        "entree en vigueur", "a compter du", "avant le", "delai", "echeance",
    )),
)

# A legal obligation which applies only to an internal public operation should
# not enter the model merely because it says "entry into force". In contrast,
# an obligation aimed at organisations can justify an investigation even before
# its market value is known.
ORGANISATION_SCOPE_TERMS = (
    "entreprise", "employeur", "professionnel", "exploitant", "operateur",
    "fournisseur", "prestataire", "association", "collectivites territoriales",
    "epci",
)
SELF_SUFFICIENT_TRIGGER_KINDS = {
    "FUNDING_OR_INCENTIVE", "PUBLIC_PURCHASE_OR_COLLECTIVITY",
    "ELIGIBILITY_OR_CERTIFICATION", "REPORTING_OR_TRACEABILITY",
    "TECHNICAL_TRANSITION",
}


# These are deterministic exits. They are deliberately narrow: they identify
# an individual/internal act, not a sector that LawRadar should permanently
# ignore.
INDIVIDUAL_OR_INTERNAL_PATTERNS = (
    r"\bautorisation d'exercer\b",
    r"\bdecision individuelle\b",
    r"\bconvention collective\b",
    r"\baccord (national|territorial|regional|departemental)\b",
    r"\bsalaires? minima\b",
)
INDIVIDUAL_OR_INTERNAL_RE = re.compile("|".join(INDIVIDUAL_OR_INTERNAL_PATTERNS), re.IGNORECASE)


def _evidence_text(candidate: dict[str, Any]) -> str:
    evidence = candidate.get("evidence", {})
    if not isinstance(evidence, dict):
        return ""
    fields = (evidence.get("title"), evidence.get("official_text_excerpt"))
    return "\n".join(item for item in fields if isinstance(item, str))


def _triggers(text: str) -> list[dict[str, Any]]:
    normalised = _normalise(text)
    found: list[dict[str, Any]] = []
    for kind, score, terms in TRIGGER_RULES:
        matched = [term for term in terms if term in normalised]
        if matched:
            found.append({"kind": kind, "score": score, "terms": matched})
    return found


def assess(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return an auditable routing decision without asserting business value."""
    evidence = candidate.get("evidence", {})
    title = evidence.get("title") if isinstance(evidence, dict) else None
    text = _evidence_text(candidate)

    if candidate.get("source_kind") == "JORF" and evidence.get("content_status") == "UNAVAILABLE":
        return {
            "schema": SCHEMA,
            "status": "PRIMARY_EVIDENCE_MISSING",
            "score": 0,
            "triggers": [],
            "reason": "PRIMARY_TEXT_EMPTY",
        }

    if isinstance(title, str) and INDIVIDUAL_OR_INTERNAL_RE.search(title):
        return {
            "schema": SCHEMA,
            "status": "NOT_A_WATCH_CANDIDATE",
            "score": 0,
            "triggers": [],
            "reason": "INDIVIDUAL_OR_INTERNAL_ACT_TITLE",
        }

    triggers = _triggers(text)
    score = sum(item["score"] for item in triggers)
    if candidate.get("source_kind") == "CONSULTDD":
        triggers.append({"kind": "OFFICIAL_PUBLIC_CONSULTATION", "score": 3, "terms": []})
        score += 3

    kinds = {item["kind"] for item in triggers}
    scope_terms = [term for term in ORGANISATION_SCOPE_TERMS if term in _normalise(text)]
    has_self_sufficient_friction = bool(kinds & SELF_SUFFICIENT_TRIGGER_KINDS)
    has_organisation_obligation = bool(scope_terms) and bool(
        kinds & {"LEGAL_OBLIGATION", "SANCTION_OR_CONTROL"}
    )
    if score >= MINIMUM_WATCH_SCORE and (has_self_sufficient_friction or has_organisation_obligation):
        return {
            "schema": SCHEMA,
            "status": "WATCH_CANDIDATE",
            "score": score,
            "triggers": triggers,
            "scope_terms": scope_terms,
            "reason": "ECONOMIC_FRICTION_DETECTED",
            "recommended_enrichment": ["PRESS", "DEMAND", "MARKET"],
        }
    return {
        "schema": SCHEMA,
        # A text without an immediately detectable economic friction is still
        # worth a compact factual reading. Claude can explain what it changes;
        # it simply must not be promoted as a business lead on that basis.
        "status": "CONTEXT_REVIEW",
        "score": score,
        "triggers": triggers,
        "scope_terms": scope_terms,
        "reason": "NO_ECONOMIC_FRICTION_EVIDENCE",
    }


def screen(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach discovery metadata to admissible records and retain exclusions."""
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for record in records:
        discovery = assess(record)
        enriched = {**record, "discovery": discovery}
        # Keep unavailable primary texts so the queue can record PRIMARY_TEXT_EMPTY
        # rather than masking a collection deficit as a harmless exclusion.
        if discovery["status"] in {"WATCH_CANDIDATE", "CONTEXT_REVIEW", "PRIMARY_EVIDENCE_MISSING"}:
            candidates.append(enriched)
        else:
            evidence = record.get("evidence", {})
            exclusions.append({
                "source_id": record.get("source_id"),
                "title": evidence.get("title") if isinstance(evidence, dict) else None,
                "reason": discovery["reason"],
                "discovery": discovery,
            })
    return candidates, exclusions
