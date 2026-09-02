#!/usr/bin/env python3
"""Produit un état Presse honnête lorsqu'aucune qualification IA n'est requise."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build(candidates: dict[str, Any], observed_at: str | None = None) -> dict[str, Any]:
    if candidates.get("schema") != "lawradar-press-candidates-v1":
        raise ValueError("Candidats Presse non pris en charge.")
    errors = candidates.get("errors", [])
    collection_successful = candidates.get("collection_successful", not errors)
    items = candidates.get("candidates", [])
    if items:
        raise ValueError("Une qualification est requise lorsque des candidats existent.")
    status = "NO_EVIDENCE" if collection_successful else "UNRESOLVED"
    summary = (
        "La collecte Presse n'a pas pu être menée à terme ; une nouvelle tentative est nécessaire."
        if not collection_successful else "Aucune couverture liée n'a été trouvée dans les sources exécutées."
    )
    limitations = (
        ["Une source obligatoire de collecte a échoué."]
        if not collection_successful
        else (["Une source d'appoint a échoué ; le résultat repose sur les sources obligatoires réussies."] if errors else ["Résultat limité aux sources exécutées et à leur fenêtre temporelle."])
    )
    return {
        "schema": "lawradar-agent-enrichment-v1",
        "agent": "press",
        "signal_id": candidates.get("signal_id"),
        "status": status,
        "observed_at_utc": observed_at or datetime.now(UTC).isoformat(),
        "summary": summary,
        "sources": [],
        "limitations": limitations,
        "details": {
            "signal_hash": candidates.get("signal_hash"),
            "window": candidates.get("window", {}),
            "queries": candidates.get("queries", []),
            "candidates_total": candidates.get("candidates_total", 0),
            "candidates_after_dedup": candidates.get("candidates_after_dedup", 0),
            "coverage_level": "NONE",
            "decisions": [],
        },
        "score": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.candidates.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
