#!/usr/bin/env python3
"""Produit une sortie Marché sans IA quand BOAMP est vide ou indisponible."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build(observations: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if observations.get("schema") != "lawradar-market-observations-v1":
        raise ValueError("Observations Marché non prises en charge.")
    status = observations.get("collection_status")
    if status not in {"NO_EVIDENCE", "UNRESOLVED"} or observations.get("observations"):
        raise ValueError("La sortie terminale Marché exige une collecte vide ou incertaine.")
    unresolved = status == "UNRESOLVED"
    return {
        "schema": "lawradar-agent-enrichment-v1",
        "agent": "market",
        "signal_id": observations["signal_id"],
        "status": "UNRESOLVED" if unresolved else "NO_EVIDENCE",
        "observed_at_utc": (now or datetime.now(UTC)).isoformat(),
        "summary": (
            "La collecte BOAMP est incomplète ou non exploitable ; aucune conclusion de marché n'est produite."
            if unresolved else "La collecte BOAMP a abouti sans avis public traçable pour les termes du signal courant."
        ),
        "sources": [],
        "limitations": (
            ["Les erreurs BOAMP empêchent de conclure à une absence d'avis."]
            if unresolved else ["BOAMP ne couvre que les marchés publics et ne mesure pas le marché global."]
        ),
        "details": {
            "signal_hash": observations["signal_hash"],
            "collection_status": status,
            "observations_total": 0,
            "conclusions": [],
        },
        "score": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.observations.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
