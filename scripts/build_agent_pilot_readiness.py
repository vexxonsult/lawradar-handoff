#!/usr/bin/env python3
"""Publie l'éligibilité déterministe des signaux aux pilotes d'enrichissement."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.run_deterministic_filters import evaluate
except ModuleNotFoundError:  # pragma: no cover - exercised by workflow CLI.
    from run_deterministic_filters import evaluate


def _text(value: Any) -> str:
    """Produce a compact, accent-insensitive comparison key."""
    import re
    import unicodedata

    raw = (value if isinstance(value, str) else "").replace("'", " ").replace("’", " ")
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()


def _research_candidate(signal: dict[str, Any], facts: dict[str, Any], research_policy: dict[str, Any]) -> tuple[int, list[str]]:
    """Score a *discarded* signal for one bounded evidence-only pass.

    This is intentionally not a second opportunity decision. It only decides
    whether Presse and Demande/Marché may look for missing, public evidence.
    The Entrepreneur remains closed for this route.
    """
    legal = facts.get("legal", {})
    title = _text(facts.get("title"))
    indicators = [_text(item) for item in research_policy["business_indicators"]]
    exclusions = [_text(item) for item in research_policy["routine_exclusions"]]
    if any(term and term in title for term in exclusions):
        return 0, ["Texte de routine explicitement exclu de la recherche élargie."]
    if legal.get("jurisdiction") != "FR":
        return 0, ["Territoire hors périmètre de la recherche élargie."]
    if legal.get("text_status") not in research_policy["eligible_legal_statuses"]:
        return 0, ["Statut juridique non éligible à la recherche élargie."]
    matched = [term for term in indicators if term and term in title]
    if not matched:
        return 0, ["Aucun indice économique déterministe dans le titre factuel."]
    score = 2  # texte français, vivant et doté d'au moins un indicateur B2B
    score += 1 if legal.get("proof_status") == "VERIFIED" else 0
    score += 1 if facts.get("affected_scope") else 0
    score += min(len(matched), 2)
    return score, [f"Indices économiques détectés : {', '.join(matched[:2])}."]


def _research_identity(entry: dict[str, Any]) -> str | None:
    """Recognize duplicate ConsultDD pages without merging unrelated texts."""
    source_id = entry.get("source_id")
    if not isinstance(source_id, str):
        return None
    match = re.search(r"(a\d+\.html)(?:[?#].*)?$", source_id, flags=re.IGNORECASE)
    return f"consultdd:{match.group(1).lower()}" if match else None


def readiness_for_signal(
    signal: dict[str, Any],
    policy: dict[str, Any],
    profile: dict[str, Any],
    research_policy: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    signal_id = signal.get("id")
    source = signal.get("source") if isinstance(signal.get("source"), dict) else {}
    radar = signal.get("radar") if isinstance(signal.get("radar"), dict) else {}
    base = {"signal_id": signal_id, "source_id": source.get("source_id"), "radar_status": radar.get("status")}
    facts = signal.get("opportunity_facts")
    if radar.get("status") == "DISCARDED" and isinstance(facts, dict):
        try:
            filters = evaluate(facts, policy, profile, now)
        except ValueError:
            filters = None
        score, reasons = _research_candidate(signal, facts, research_policy)
        access = (filters or {}).get("operator_access", {})
        if score >= int(research_policy["minimum_score"]) and access.get("allow_external_collection") is True:
            return {
                **base,
                "status": "RESEARCH_CANDIDATE",
                "ready_for_pilots": True,
                "client_scope": "RESEARCH_ONLY",
                "entrepreneur_allowed": False,
                "research_score": score,
                "recommended_next_step": "RUN_BOUNDED_PRESS_AND_MARKET_RESEARCH",
                "reasons": [*reasons, "La recherche n'autorise aucune décision Entrepreneur."],
                "filters": filters,
            }
        return {
            **base,
            "status": "NOT_RETAINED",
            "ready_for_pilots": False,
            "client_scope": "NONE",
            "entrepreneur_allowed": False,
            "research_score": score,
            "recommended_next_step": "NO_ACTION",
            "reasons": reasons if score == 0 else [*reasons, "La porte opérateur interdit une collecte externe."],
            "filters": filters,
        }
    if radar.get("status") != "RETAINED":
        return {**base, "status": "NOT_RETAINED", "ready_for_pilots": False, "client_scope": "NONE", "entrepreneur_allowed": False, "recommended_next_step": "NO_ACTION", "reasons": ["Le Radar n'a pas retenu ce signal."], "filters": None}
    if not isinstance(facts, dict):
        return {**base, "status": "WAITING_FOR_OPPORTUNITY_FACTS", "ready_for_pilots": False, "client_scope": "NONE", "entrepreneur_allowed": False, "recommended_next_step": "WAIT_FOR_NEXT_MOTOR_DELIVERY", "reasons": ["Le signal provient d'une livraison antérieure aux faits d'opportunité versionnés."], "filters": None}
    try:
        filters = evaluate(facts, policy, profile, now)
    except ValueError as caught:
        return {**base, "status": "INVALID_OPPORTUNITY_FACTS", "ready_for_pilots": False, "client_scope": "NONE", "entrepreneur_allowed": False, "recommended_next_step": "REVIEW_MOTOR_DELIVERY", "reasons": [str(caught)], "filters": None}
    access = filters["operator_access"]
    if filters["final_constraint"] == "DISCARD":
        status, next_step, ready = "DISCARDED_BY_FILTERS", "NO_EXTERNAL_COLLECTION", False
        reasons = [*filters["compliance"]["reasons"], *filters["feasibility"]["reasons"]]
    elif not access["allow_external_collection"]:
        status, next_step, ready = "HOLD_BY_OPERATOR_ACCESS", "LEGAL_ROLE_CHECK_ONLY", False
        reasons = access["reasons"]
    else:
        status, next_step, ready = "READY_FOR_PILOTS", "RUN_PRESS_THEN_MARKET_IF_SCOPE_FITS", True
        reasons = ["Le signal retenu porte des faits valides et passe la porte opérateur."]
    return {
        **base,
        "status": status,
        "ready_for_pilots": ready,
        "client_scope": "FULL_PIPELINE" if ready else "NONE",
        "entrepreneur_allowed": bool(ready and filters["final_constraint"] == "PASS"),
        "recommended_next_step": next_step,
        "reasons": reasons,
        "filters": filters,
    }


def build(
    dossier: dict[str, Any],
    policy: dict[str, Any],
    profile: dict[str, Any],
    now: datetime | None = None,
    research_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if dossier.get("schema") not in {"lawradar-universal-signal-v1", "lawradar-universal-signal-v2"}:
        raise ValueError("Dossier universel non pris en charge.")
    signals = dossier.get("signals")
    if not isinstance(signals, list):
        raise ValueError("Liste de signaux invalide.")
    if not isinstance(research_policy, dict) or research_policy.get("schema") != "lawradar-research-candidate-policy-v1":
        raise ValueError("Politique de candidats de recherche invalide.")
    for key in ("maximum_signals_per_run", "minimum_score"):
        if not isinstance(research_policy.get(key), int) or research_policy[key] < 1:
            raise ValueError(f"Politique de recherche invalide : {key}.")
    for key in ("eligible_legal_statuses", "business_indicators", "routine_exclusions"):
        if not isinstance(research_policy.get(key), list) or not all(isinstance(item, str) for item in research_policy[key]):
            raise ValueError(f"Politique de recherche invalide : {key}.")
    current = now or datetime.now(UTC)
    entries = [readiness_for_signal(item, policy, profile, research_policy, current) for item in signals if isinstance(item, dict)]
    candidates = sorted(
        (item for item in entries if item["status"] == "RESEARCH_CANDIDATE"),
        key=lambda item: (-int(item["research_score"]), str(item.get("signal_id"))),
    )
    selected: list[dict[str, Any]] = []
    identities: set[str] = set()
    maximum = int(research_policy["maximum_signals_per_run"])
    for candidate in candidates:
        identity = _research_identity(candidate)
        if identity and identity in identities:
            candidate.update({
                "status": "RESEARCH_CANDIDATE_DEFERRED",
                "ready_for_pilots": False,
                "client_scope": "NONE",
                "entrepreneur_allowed": False,
                "recommended_next_step": "NO_ACTION",
                "reasons": [*candidate["reasons"], "Doublon de source officielle : une seule recherche est autorisée."],
            })
            continue
        if len(selected) < maximum:
            selected.append(candidate)
            if identity:
                identities.add(identity)
            continue
        candidate.update({
            "status": "RESEARCH_CANDIDATE_DEFERRED",
            "ready_for_pilots": False,
            "client_scope": "NONE",
            "entrepreneur_allowed": False,
            "recommended_next_step": "WAIT_FOR_NEXT_MOTOR_DELIVERY",
            "reasons": [*candidate["reasons"], "Plafond de recherche bornée atteint pour cette livraison."],
        })
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "schema": "lawradar-agent-pilot-readiness-v1",
        "generated_at_utc": current.isoformat(),
        "source_run": dossier.get("run", {}),
        "signals": entries,
        "summary": {
            "signal_count": len(entries),
            "ready_for_pilots_count": sum(item["ready_for_pilots"] for item in entries),
            "research_candidates_selected": sum(item["status"] == "RESEARCH_CANDIDATE" for item in entries),
            "counts_by_status": counts,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--research-policy", type=Path, default=Path("config/research-candidate-policy-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.dossier.read_text(encoding="utf-8")), json.loads(args.policy.read_text(encoding="utf-8")), json.loads(args.profile.read_text(encoding="utf-8")), research_policy=json.loads(args.research_policy.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
