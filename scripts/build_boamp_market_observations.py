#!/usr/bin/env python3
"""Transforme les avis BOAMP compacts en observations Marché traçables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.fetch_boamp_data import facts_hash
    from scripts.run_deterministic_filters import validate_facts
except ModuleNotFoundError:  # pragma: no cover - exercised by workflow CLI.
    from fetch_boamp_data import facts_hash
    from run_deterministic_filters import validate_facts


def excerpt(title: str) -> str:
    return " ".join(title.split()[:25])


def build(facts: dict[str, Any], boamp: dict[str, Any]) -> dict[str, Any]:
    validate_facts(facts)
    if boamp.get("schema") != "lawradar-market-demand-boamp-v1":
        raise ValueError("Résultat BOAMP non pris en charge.")
    if boamp.get("signal_id") != facts["signal_id"] or boamp.get("signal_hash") != facts_hash(facts):
        raise ValueError("Résultat BOAMP rattaché à un autre signal.")
    status = boamp.get("collection_status")
    if status not in {"COMPLETED", "NO_EVIDENCE", "UNRESOLVED"}:
        raise ValueError("Statut BOAMP invalide.")
    records = boamp.get("observations", [])
    if not isinstance(records, list):
        raise ValueError("Observations BOAMP invalides.")
    observations: list[dict[str, Any]] = []
    errors = list(boamp.get("errors", [])) if isinstance(boamp.get("errors"), list) else []
    for record in records:
        if not isinstance(record, dict):
            errors.append({"error": "Avis BOAMP non structuré."})
            continue
        url, title = record.get("url"), record.get("title")
        if not isinstance(url, str) or not url or not isinstance(title, str) or not title.strip():
            errors.append({"id": record.get("id"), "error": "Avis BOAMP sans URL ou objet traçable."})
            continue
        observations.append({
            "url": url,
            "title": " ".join(title.split()),
            "provider": "BOAMP",
            "actor": record.get("buyer") if isinstance(record.get("buyer"), str) and record["buyer"].strip() else "Acheteur non communiqué",
            "observation_type": "PUBLIC_PROCUREMENT",
            "geography": "FR",
            "retrieved_at_utc": boamp.get("collected_at_utc"),
            "excerpt": excerpt(title),
        })
    collection_status = "UNRESOLVED" if status == "UNRESOLVED" or errors else status
    if collection_status == "NO_EVIDENCE":
        observations = []
    return {
        "schema": "lawradar-market-observations-v1",
        "signal_id": facts["signal_id"],
        "signal_hash": facts_hash(facts),
        "collected_at_utc": boamp.get("collected_at_utc"),
        "collection_status": collection_status,
        "observations": observations,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--boamp", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        json.loads(args.facts.read_text(encoding="utf-8")),
        json.loads(args.boamp.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
