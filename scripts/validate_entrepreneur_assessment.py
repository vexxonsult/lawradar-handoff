#!/usr/bin/env python3
"""Valide que l'Entrepreneur ne décide qu'à partir des éléments transmis."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.merge_agent_enrichment import validate_enrichment
except ModuleNotFoundError:  # pragma: no cover - exercised by workflow CLI.
    from merge_agent_enrichment import validate_enrichment


SUPPORT_AGENTS = {"press", "demand", "market"}
TERMINAL = {"COMPLETED", "NO_EVIDENCE"}
DETAIL_KEYS = {"signal_hash", "support_statuses", "decision", "gaps", "test_protocol"}
DECISIONS = {"WATCH", "INVESTIGATE", "TEST", "DISCARD"}
PROTOCOL_KEYS = {"hypothesis", "method", "success_signal", "stop_condition", "max_duration_days"}


def validate(input_data: dict[str, Any], assessment: dict[str, Any]) -> None:
    if input_data.get("schema") != "lawradar-entrepreneur-input-v1":
        raise ValueError("Entrée Entrepreneur non prise en charge.")
    validate_enrichment(assessment)
    if assessment.get("agent") != "entrepreneur":
        raise ValueError("La sortie doit provenir de l'agent Entrepreneur.")
    details = assessment["details"]
    if set(details) != DETAIL_KEYS or details.get("signal_hash") != input_data.get("signal_hash"):
        raise ValueError("Détails Entrepreneur invalides ou non liés au signal.")
    statuses = {agent: input_data.get("support", {}).get(agent, {}).get("status") for agent in SUPPORT_AGENTS}
    if details.get("support_statuses") != statuses or details.get("decision") not in DECISIONS:
        raise ValueError("Statuts amont ou décision Entrepreneur invalides.")
    if not isinstance(details.get("gaps"), list) or not all(isinstance(item, str) and item for item in details["gaps"]):
        raise ValueError("Manques Entrepreneur invalides.")
    if assessment.get("signal_id") != input_data.get("signal_id"):
        raise ValueError("La sortie Entrepreneur cible un autre signal.")
    allowed_urls = set(input_data.get("allowed_source_urls", []))
    source_urls = {item.get("url") for item in assessment["sources"] if isinstance(item, dict)}
    if not source_urls <= allowed_urls:
        raise ValueError("Une source Entrepreneur n'est pas issue des éléments transmis.")
    incomplete = {agent for agent, status in statuses.items() if status not in TERMINAL}
    protocol = details["test_protocol"]
    if protocol is not None:
        if not isinstance(protocol, dict) or set(protocol) != PROTOCOL_KEYS or not all(isinstance(protocol[key], str) and protocol[key] for key in PROTOCOL_KEYS - {"max_duration_days"}):
            raise ValueError("Protocole de test Entrepreneur invalide.")
        if not isinstance(protocol["max_duration_days"], int) or not 1 <= protocol["max_duration_days"] <= 30:
            raise ValueError("Durée de test Entrepreneur invalide.")
    if incomplete:
        if assessment["status"] != "UNRESOLVED" or details["decision"] != "INVESTIGATE" or not details["gaps"]:
            raise ValueError("Des enrichissements amont incomplets imposent INVESTIGATE et UNRESOLVED.")
        return
    if assessment["status"] != "COMPLETED":
        raise ValueError("Une décision Entrepreneur avec les trois apports terminés doit être COMPLETED.")
    citations = {int(value) for value in re.findall(r"\[(\d+)\]", assessment["summary"])}
    if not source_urls or not citations or max(citations) > len(assessment["sources"]):
        raise ValueError("La synthèse Entrepreneur doit citer des sources transmises.")
    if details["decision"] == "TEST":
        positive_support = {"demand", "market"} & {agent for agent, status in statuses.items() if status == "COMPLETED"}
        if not positive_support or protocol is None:
            raise ValueError("TEST exige un apport Demande ou Marché positif et un protocole réversible.")
    elif protocol is not None:
        raise ValueError("Un protocole est réservé à la décision TEST.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--assessment", type=Path, required=True)
    args = parser.parse_args()
    validate(json.loads(args.input.read_text(encoding="utf-8")), json.loads(args.assessment.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
