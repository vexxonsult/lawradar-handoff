#!/usr/bin/env python3
"""Valide une livraison moteur et rend son dashboard déterministe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.render_dashboard import render_dashboard
    from scripts.run_deterministic_filters import validate_facts
except ModuleNotFoundError:  # Exécution directe : python scripts/render_motor_delivery.py
    from render_dashboard import render_dashboard
    from run_deterministic_filters import validate_facts


FLOW_FIELDS = (
    "id", "label", "title", "money_sentence", "explanation", "payer",
    "recipient", "amount", "effective_date", "certainty", "next_action",
)
FLOW_FIELD_SET = set(FLOW_FIELDS)
READING_FIELDS = (
    "consequence", "affected_actors", "beneficiaries", "constrained_parties",
    "potential_service_partners", "unknowns",
)


def require_text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Champ textuel obligatoire invalide : {name}.")


def validate_reading(reading: Any, index: int) -> None:
    if not isinstance(reading, dict) or set(reading) != set(READING_FIELDS):
        raise ValueError(f"Lecture de texte invalide : {index}.")
    require_text(reading.get("consequence"), f"opportunities[{index}].reading.consequence")
    for field in READING_FIELDS[1:]:
        value = reading.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError(f"Lecture de texte invalide : {index}.{field}.")


def validate_delivery(delivery: dict[str, Any]) -> None:
    if delivery.get("schema") != "lawradar-motor-delivery-v1":
        raise ValueError("Schéma de livraison moteur non pris en charge.")
    run = delivery.get("run")
    if not isinstance(run, dict):
        raise ValueError("Bloc run invalide.")
    for name in ("report_date", "coverage", "summary"):
        require_text(run.get(name), f"run.{name}")
    opportunities = delivery.get("opportunities")
    if not isinstance(opportunities, list):
        raise ValueError("Bloc opportunities invalide.")
    for index, item in enumerate(opportunities):
        if not isinstance(item, dict):
            raise ValueError(f"Opportunité {index} invalide.")
        require_text(item.get("source_id"), f"opportunities[{index}].source_id")
        if item.get("status") not in {"RETAINED", "DISCARDED", "UNRESOLVED"}:
            raise ValueError(f"Statut d'opportunité invalide : {index}.")
        require_text(item.get("reason"), f"opportunities[{index}].reason")
        facts = item.get("facts")
        if not isinstance(facts, dict):
            raise ValueError(f"Faits d'opportunité absents : {index}.")
        try:
            validate_facts(facts)
        except ValueError as caught:
            raise ValueError(f"Faits d'opportunité invalides : {index}.") from caught
        if facts["signal_id"] != item["source_id"]:
            raise ValueError(f"Faits rattachés au mauvais signal : {index}.")
        # Backward-compatible for historical deliveries. New batch results are
        # required to carry the field by CANDIDATE_RESULT_SCHEMA.
        if "reading" in item:
            validate_reading(item["reading"], index)
    flows = delivery.get("money_flows")
    if not isinstance(flows, list):
        raise ValueError("Bloc money_flows invalide.")
    seen_ids: set[str] = set()
    for index, flow in enumerate(flows):
        if not isinstance(flow, dict) or set(flow) != FLOW_FIELD_SET:
            raise ValueError(f"Flux {index} non conforme au contrat.")
        for name in FLOW_FIELDS:
            require_text(flow[name], f"money_flows[{index}].{name}")
        if flow["id"] in seen_ids:
            raise ValueError(f"Identifiant de flux dupliqué : {flow['id']}.")
        seen_ids.add(flow["id"])


def dashboard_input(delivery: dict[str, Any]) -> dict[str, Any]:
    validate_delivery(delivery)
    return {
        "schema": "lawradar-dashboard-input-v1",
        "report_date": delivery["run"]["report_date"],
        "headline": delivery["run"]["summary"],
        "coverage": delivery["run"]["coverage"],
        "flows": [
            {name: flow[name] for name in FLOW_FIELDS if name != "id"}
            for flow in delivery["money_flows"]
        ],
        "readings": [
            {
                "title": item["facts"]["title"],
                "status": item["status"],
                "reason": item["reason"],
                "reading": item.get("reading", {
                    "consequence": item["reason"], "affected_actors": [], "beneficiaries": [],
                    "constrained_parties": [], "potential_service_partners": [],
                    "unknowns": ["Lecture structurée indisponible pour cette livraison historique."],
                }),
            }
            for item in delivery["opportunities"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dashboard", type=Path, required=True)
    args = parser.parse_args()
    delivery = json.loads(args.input.read_text(encoding="utf-8"))
    result = dashboard_input(delivery)
    args.dashboard.parent.mkdir(parents=True, exist_ok=True)
    args.dashboard.write_text(render_dashboard(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
