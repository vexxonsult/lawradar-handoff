#!/usr/bin/env python3
"""Construit les observations Demande V2 à partir de BOAMP, sans IA."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.fetch_boamp_data import facts_hash, parse_deadline
    from scripts.run_deterministic_filters import validate_facts
except ModuleNotFoundError:  # pragma: no cover - exercised by workflow CLI.
    from fetch_boamp_data import facts_hash, parse_deadline
    from run_deterministic_filters import validate_facts


def disabled_indicators() -> dict[str, Any]:
    return {
        "trends": {"status": "DISABLED", "experimental_manual_only": True, "ratio_7d_vs_prior_83d": None, "surge_detected": None},
        "autocomplete": {"status": "DISABLED", "experimental_manual_only": True, "intent_terms_found": [], "commercial_intent": None},
    }


def classify_institutional(records: list[dict[str, Any]]) -> dict[str, Any]:
    buyers = {item.get("buyer") for item in records if isinstance(item.get("buyer"), str) and item["buyer"]}
    if not records:
        status = "NONE"
    elif len(records) >= 3 or len(buyers) >= 2:
        status = "HIGH_INSTITUTIONAL_DEMAND"
    else:
        status = "INSTITUTIONAL_DEMAND_OBSERVED"
    return {"status": status, "open_tender_count": sum(item["notice_kind"] == "TENDER" for item in records), "pre_information_count": sum(item["notice_kind"] == "PRE_INFORMATION" for item in records), "distinct_buyer_count": len(buyers)}


def build_blocked(facts: dict[str, Any], gate: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Record a gate hold without collecting or claiming a negative result."""
    validate_facts(facts)
    access = gate.get("operator_access") if isinstance(gate.get("operator_access"), dict) else None
    if not access or access.get("allow_external_collection") is not False:
        raise ValueError("La sortie bloquée exige une porte opérateur fermée.")
    return {
        "schema": "lawradar-demand-observations-v2", "signal_id": facts["signal_id"], "signal_hash": facts_hash(facts),
        "collected_at_utc": (now or datetime.now(UTC)).isoformat(), "collection_status": "SKIPPED_BY_OPERATOR_GATE",
        "indicators": {**disabled_indicators(), "institutional": {"status": "SKIPPED_BY_OPERATOR_GATE", "open_tender_count": 0, "pre_information_count": 0, "distinct_buyer_count": 0}},
        "observations": [], "errors": [{"reason": "OPERATOR_ACCESS_HOLD", "details": access.get("reasons", [])}],
    }


def build(facts: dict[str, Any], boamp: dict[str, Any]) -> dict[str, Any]:
    validate_facts(facts)
    if boamp.get("schema") != "lawradar-market-demand-boamp-v1":
        raise ValueError("Résultat BOAMP non pris en charge.")
    if boamp.get("signal_id") != facts["signal_id"] or boamp.get("signal_hash") != facts_hash(facts):
        raise ValueError("Résultat BOAMP rattaché à un autre signal.")
    status = boamp.get("collection_status")
    if status not in {"COMPLETED", "NO_EVIDENCE", "UNRESOLVED"}:
        raise ValueError("Statut BOAMP invalide.")
    collected_at = boamp.get("collected_at_utc")
    try:
        collected = datetime.fromisoformat(str(collected_at).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as caught:
        raise ValueError("Date de collecte BOAMP invalide.") from caught
    records: list[dict[str, Any]] = []
    errors = list(boamp.get("errors", [])) if isinstance(boamp.get("errors"), list) else []
    for record in boamp.get("observations", []):
        if not isinstance(record, dict) or record.get("notice_kind") not in {"TENDER", "PRE_INFORMATION"}:
            continue
        deadline = parse_deadline(record.get("response_deadline"))
        if record["notice_kind"] == "TENDER" and (deadline is None or deadline < collected):
            continue
        url, title = record.get("url"), record.get("title")
        if not isinstance(url, str) or not url or not isinstance(title, str) or not title.strip():
            errors.append({"id": record.get("id"), "error": "Avis BOAMP pertinent sans URL ou objet traçable."})
            continue
        records.append({"url": url, "title": " ".join(title.split()), "buyer": record.get("buyer"), "notice_kind": record["notice_kind"], "published_at": record.get("published_at"), "response_deadline": record.get("response_deadline")})
    collection_status = "UNRESOLVED" if status == "UNRESOLVED" or errors else "COMPLETED"
    institutional = classify_institutional(records) if collection_status == "COMPLETED" else {"status": "UNRESOLVED", "open_tender_count": 0, "pre_information_count": 0, "distinct_buyer_count": 0}
    observations = []
    for item in records:
        deadline = parse_deadline(item["response_deadline"])
        period = f"jusqu'au {deadline.date().isoformat()}" if deadline else str(item.get("published_at") or collected.date().isoformat())
        observations.append({"url": item["url"], "title": item["title"], "provider": "BOAMP", "metric": "active_public_tender_notice" if item["notice_kind"] == "TENDER" else "public_preinformation_notice", "value": 1, "unit": "notice", "period": period, "geography": "FR", "retrieved_at_utc": collected_at})
    return {
        "schema": "lawradar-demand-observations-v2", "signal_id": facts["signal_id"], "signal_hash": facts_hash(facts),
        "collected_at_utc": collected_at, "collection_status": collection_status,
        "indicators": {**disabled_indicators(), "institutional": institutional}, "observations": observations, "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--boamp", type=Path)
    parser.add_argument("--operator-gate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    facts = json.loads(args.facts.read_text(encoding="utf-8"))
    if bool(args.boamp) == bool(args.operator_gate):
        raise ValueError("Fournir exactement BOAMP ou la porte opérateur.")
    result = build(facts, json.loads(args.boamp.read_text(encoding="utf-8"))) if args.boamp else build_blocked(facts, json.loads(args.operator_gate.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
