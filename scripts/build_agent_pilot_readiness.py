#!/usr/bin/env python3
"""Publie l'éligibilité déterministe des signaux aux pilotes d'enrichissement."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.run_deterministic_filters import evaluate
except ModuleNotFoundError:  # pragma: no cover - exercised by workflow CLI.
    from run_deterministic_filters import evaluate


def readiness_for_signal(signal: dict[str, Any], policy: dict[str, Any], profile: dict[str, Any], now: datetime) -> dict[str, Any]:
    signal_id = signal.get("id")
    source = signal.get("source") if isinstance(signal.get("source"), dict) else {}
    radar = signal.get("radar") if isinstance(signal.get("radar"), dict) else {}
    base = {"signal_id": signal_id, "source_id": source.get("source_id"), "radar_status": radar.get("status")}
    if radar.get("status") != "RETAINED":
        return {**base, "status": "NOT_RETAINED", "ready_for_pilots": False, "recommended_next_step": "NO_ACTION", "reasons": ["Le Radar n'a pas retenu ce signal."], "filters": None}
    facts = signal.get("opportunity_facts")
    if not isinstance(facts, dict):
        return {**base, "status": "WAITING_FOR_OPPORTUNITY_FACTS", "ready_for_pilots": False, "recommended_next_step": "WAIT_FOR_NEXT_MOTOR_DELIVERY", "reasons": ["Le signal provient d'une livraison antérieure aux faits d'opportunité versionnés."], "filters": None}
    try:
        filters = evaluate(facts, policy, profile, now)
    except ValueError as caught:
        return {**base, "status": "INVALID_OPPORTUNITY_FACTS", "ready_for_pilots": False, "recommended_next_step": "REVIEW_MOTOR_DELIVERY", "reasons": [str(caught)], "filters": None}
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
    return {**base, "status": status, "ready_for_pilots": ready, "recommended_next_step": next_step, "reasons": reasons, "filters": filters}


def build(dossier: dict[str, Any], policy: dict[str, Any], profile: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if dossier.get("schema") not in {"lawradar-universal-signal-v1", "lawradar-universal-signal-v2"}:
        raise ValueError("Dossier universel non pris en charge.")
    signals = dossier.get("signals")
    if not isinstance(signals, list):
        raise ValueError("Liste de signaux invalide.")
    current = now or datetime.now(UTC)
    entries = [readiness_for_signal(item, policy, profile, current) for item in signals if isinstance(item, dict)]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "schema": "lawradar-agent-pilot-readiness-v1",
        "generated_at_utc": current.isoformat(),
        "source_run": dossier.get("run", {}),
        "signals": entries,
        "summary": {"signal_count": len(entries), "ready_for_pilots_count": sum(item["ready_for_pilots"] for item in entries), "counts_by_status": counts},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.dossier.read_text(encoding="utf-8")), json.loads(args.policy.read_text(encoding="utf-8")), json.loads(args.profile.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
