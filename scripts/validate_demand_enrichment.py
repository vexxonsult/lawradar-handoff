#!/usr/bin/env python3
"""Valide qu'une sortie Demande reste limitée à des observations mesurées."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.merge_agent_enrichment import validate_enrichment
except ModuleNotFoundError:  # pragma: no cover - exercised by the workflow CLI.
    from merge_agent_enrichment import validate_enrichment


COLLECTION_STATUSES = {"COMPLETED", "NO_EVIDENCE", "UNRESOLVED"}
INTERPRETATIONS = {"ATTENTION", "SEARCH_INTEREST", "COMMERCIAL_INTENT", "NOT_RELEVANT", "AMBIGUOUS"}
DETAIL_KEYS = {"signal_hash", "collection_status", "observations_total", "conclusions"}
OBSERVATION_KEYS = {"url", "title", "provider", "metric", "value", "unit", "period", "geography", "retrieved_at_utc"}


def validate(observations: dict[str, Any], enrichment: dict[str, Any]) -> None:
    if observations.get("schema") != "lawradar-demand-observations-v1":
        raise ValueError("Observations Demande non prises en charge.")
    validate_enrichment(enrichment)
    if enrichment.get("agent") != "demand":
        raise ValueError("La sortie doit provenir de l'agent Demande.")
    details = enrichment["details"]
    if set(details) != DETAIL_KEYS:
        raise ValueError("Détails Demande invalides.")
    if enrichment["signal_id"] != observations.get("signal_id") or details["signal_hash"] != observations.get("signal_hash"):
        raise ValueError("La sortie Demande ne correspond pas au signal mesuré.")
    if details["collection_status"] not in COLLECTION_STATUSES or not isinstance(details["observations_total"], int) or not isinstance(details["conclusions"], list):
        raise ValueError("Statut ou conclusions Demande invalides.")
    items = observations.get("observations", [])
    for item in items:
        if not isinstance(item, dict) or not OBSERVATION_KEYS <= set(item):
            raise ValueError("Une observation Demande doit contenir sa métrique, période, zone et provenance.")
        if not isinstance(item["url"], str) or not item["url"] or not isinstance(item["metric"], str) or not item["metric"]:
            raise ValueError("URL ou métrique Demande invalide.")
    if details["observations_total"] != len(items):
        raise ValueError("Le nombre d'observations Demande ne correspond pas à l'entrée.")
    urls = {item["url"] for item in items}
    source_urls = {item.get("url") for item in enrichment["sources"] if isinstance(item, dict)}
    if not source_urls <= urls:
        raise ValueError("Une source Demande n'est pas issue des observations mesurées.")
    relevant: set[str] = set()
    for item in details["conclusions"]:
        if not isinstance(item, dict) or item.get("url") not in urls or item.get("interpretation") not in INTERPRETATIONS or not isinstance(item.get("why"), str):
            raise ValueError("Conclusion Demande invalide ou hors observations.")
        if item["interpretation"] in {"ATTENTION", "SEARCH_INTEREST", "COMMERCIAL_INTENT"}:
            relevant.add(item["url"])
    if enrichment["status"] == "COMPLETED":
        if not source_urls or not source_urls <= relevant:
            raise ValueError("COMPLETED exige des observations Demande pertinentes.")
        citations = {int(value) for value in re.findall(r"\[(\d+)\]", enrichment["summary"])}
        if not citations or max(citations) > len(enrichment["sources"]):
            raise ValueError("La synthèse Demande doit renvoyer vers ses sources.")
    if enrichment["status"] == "NO_EVIDENCE":
        if items or observations.get("errors") or details["collection_status"] != "COMPLETED" or source_urls:
            raise ValueError("NO_EVIDENCE exige une collecte aboutie sans observation.")
    if enrichment["status"] == "UNRESOLVED" and not (observations.get("errors") or details["collection_status"] == "UNRESOLVED" or any(item.get("interpretation") == "AMBIGUOUS" for item in details["conclusions"])):
        raise ValueError("UNRESOLVED doit conserver une cause d'incertitude.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--enrichment", type=Path, required=True)
    args = parser.parse_args()
    validate(json.loads(args.observations.read_text(encoding="utf-8")), json.loads(args.enrichment.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
