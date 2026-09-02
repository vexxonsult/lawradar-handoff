#!/usr/bin/env python3
"""Ajoute un enrichissement sourcé sans modifier le Radar ni la preuve."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


AGENTS = {"press", "demand", "market"}
STATUSES = {"COMPLETED", "NO_EVIDENCE", "UNRESOLVED", "FAILED"}


def validate_enrichment(enrichment: dict[str, Any]) -> None:
    required = {
        "schema", "agent", "signal_id", "status", "observed_at_utc",
        "summary", "sources", "limitations", "details", "score",
    }
    if set(enrichment) != required:
        raise ValueError("Structure d'enrichissement invalide.")
    if enrichment["schema"] != "lawradar-agent-enrichment-v1":
        raise ValueError("Schéma d'enrichissement non pris en charge.")
    if enrichment["agent"] not in AGENTS:
        raise ValueError("Agent d'enrichissement inconnu.")
    if enrichment["status"] not in STATUSES:
        raise ValueError("Statut d'enrichissement invalide.")
    if not isinstance(enrichment["signal_id"], str) or not enrichment["signal_id"]:
        raise ValueError("Signal cible invalide.")
    if not isinstance(enrichment["observed_at_utc"], str) or not enrichment["observed_at_utc"]:
        raise ValueError("Date d'observation invalide.")
    if not isinstance(enrichment["summary"], str) or not enrichment["summary"]:
        raise ValueError("Résumé d'enrichissement invalide.")
    if not isinstance(enrichment["sources"], list) or not isinstance(enrichment["limitations"], list) or not isinstance(enrichment["details"], dict):
        raise ValueError("Sources, limites ou détails invalides.")
    if enrichment["score"] is not None:
        raise ValueError("Aucun score n'est autorisé avant une méthode versionnée.")


def merge(dossier: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
    if dossier.get("schema") != "lawradar-universal-signal-v1":
        raise ValueError("Dossier universel non pris en charge.")
    validate_enrichment(enrichment)
    result = copy.deepcopy(dossier)
    matching = [item for item in result.get("signals", []) if item.get("id") == enrichment["signal_id"]]
    if len(matching) != 1:
        raise ValueError("Le signal cible est absent ou dupliqué.")
    slot = matching[0].get("enrichments", {}).get(enrichment["agent"])
    if not isinstance(slot, dict):
        raise ValueError("Cet emplacement d'enrichissement n'est pas disponible.")
    previous_results = slot.get("previous_results", [])
    attempts = int(slot.get("attempts", 0))
    if slot.get("status") == "PENDING" and slot.get("result") is None:
        previous_results = []
        attempts = 0
    elif slot.get("status") == "UNRESOLVED" and isinstance(slot.get("result"), dict) and attempts == 1:
        previous_results = [*previous_results, slot["result"]]
    else:
        raise ValueError("Cet emplacement d'enrichissement n'est pas disponible.")
    matching[0]["enrichments"][enrichment["agent"]] = {
        "status": enrichment["status"],
        "result": enrichment,
        "attempts": attempts + 1,
        "previous_results": previous_results,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--enrichment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dossier = json.loads(args.dossier.read_text(encoding="utf-8"))
    enrichment = json.loads(args.enrichment.read_text(encoding="utf-8"))
    merged = merge(dossier, enrichment)
    args.output.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
