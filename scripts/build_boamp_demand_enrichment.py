#!/usr/bin/env python3
"""Produit un enrichissement Demande borné à la demande publique BOAMP."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build(observations: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if observations.get("schema") != "lawradar-demand-observations-v2":
        raise ValueError("Observations Demande non prises en charge.")
    status = observations.get("collection_status")
    items = observations.get("observations")
    if status not in {"COMPLETED", "NO_EVIDENCE", "UNRESOLVED"} or not isinstance(items, list):
        raise ValueError("Statut ou observations Demande invalides.")
    if status == "UNRESOLVED":
        output_status, sources, conclusions = "UNRESOLVED", [], []
        summary = "La collecte de demande publique BOAMP est incomplète ou non exploitable ; aucune conclusion n'est produite."
        limitations = ["Les erreurs BOAMP empêchent de conclure à une absence de demande publique."]
    elif not items:
        output_status, sources, conclusions = "NO_EVIDENCE", [], []
        summary = "La collecte BOAMP a abouti sans appel d'offres public actif et traçable pour les termes du signal courant."
        limitations = ["BOAMP ne couvre que la demande publique formalisée, pas la demande générale."]
    else:
        output_status = "COMPLETED"
        sources = [{"url": item["url"], "title": item["title"]} for item in items]
        conclusions = [{"url": item["url"], "interpretation": "COMMERCIAL_INTENT", "why": "L'avis BOAMP actif exprime un besoin d'achat public formalisé."} for item in items]
        citations = " ".join(f"[{index}]" for index in range(1, len(sources) + 1))
        summary = f"BOAMP recense {len(items)} appel(s) d'offres public(s) actif(s) correspondant aux termes du signal courant. {citations}"
        limitations = ["Ces avis prouvent une demande publique formalisée, pas une taille de marché ni une demande privée."]
    return {
        "schema": "lawradar-agent-enrichment-v1", "agent": "demand", "signal_id": observations["signal_id"],
        "status": output_status, "observed_at_utc": (now or datetime.now(UTC)).isoformat(),
        "summary": summary, "sources": sources, "limitations": limitations,
        "details": {"signal_hash": observations["signal_hash"], "collection_status": status, "observations_total": len(items), "conclusions": conclusions, "indicators": observations["indicators"]},
        "score": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.observations.read_text(encoding="utf-8"))), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
