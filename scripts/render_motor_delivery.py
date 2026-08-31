#!/usr/bin/env python3
"""Valide une livraison moteur et rend son dashboard déterministe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.render_dashboard import render_dashboard


FLOW_FIELDS = (
    "id", "label", "title", "money_sentence", "explanation", "payer",
    "recipient", "amount", "effective_date", "certainty", "next_action",
)
FLOW_FIELD_SET = set(FLOW_FIELDS)


def require_text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Champ textuel obligatoire invalide : {name}.")


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
