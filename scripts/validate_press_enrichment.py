#!/usr/bin/env python3
"""Vérifie qu'une sortie Presse reste liée aux candidats réellement collectés."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:  # Works both as `python -m` in tests and as a standalone workflow script.
    from scripts.merge_agent_enrichment import validate_enrichment
except ModuleNotFoundError:  # pragma: no cover - exercised by the workflow CLI.
    from merge_agent_enrichment import validate_enrichment


RELEVANCE = {"DIRECT", "CONTEXTUAL", "NOT_LINKED", "AMBIGUOUS"}
COVERAGE = {"NONE", "LOW", "MEDIUM", "HIGH"}
DETAIL_KEYS = {
    "signal_hash", "window", "queries", "candidates_total",
    "candidates_after_dedup", "coverage_level", "decisions",
}


def validate(candidates: dict[str, Any], enrichment: dict[str, Any]) -> None:
    if candidates.get("schema") != "lawradar-press-candidates-v1":
        raise ValueError("Candidats Presse non pris en charge.")
    validate_enrichment(enrichment)
    if enrichment.get("agent") != "press":
        raise ValueError("La sortie doit provenir de l'agent Presse.")
    details = enrichment["details"]
    if set(details) != DETAIL_KEYS:
        raise ValueError("Détails Presse invalides.")
    if enrichment["signal_id"] != candidates.get("signal_id") or details["signal_hash"] != candidates.get("signal_hash"):
        raise ValueError("La sortie Presse ne correspond pas au signal collecté.")
    if details["coverage_level"] not in COVERAGE or not isinstance(details["decisions"], list):
        raise ValueError("Couverture ou décisions Presse invalides.")
    candidate_urls = {item.get("url") for item in candidates.get("candidates", []) if isinstance(item, dict)}
    source_urls = set()
    for item in enrichment["sources"]:
        if not isinstance(item, dict) or item.get("url") not in candidate_urls:
            raise ValueError("Une source Presse n'est pas issue des candidats collectés.")
        source_urls.add(item["url"])
    direct_or_contextual = set()
    for item in details["decisions"]:
        if not isinstance(item, dict) or item.get("url") not in candidate_urls or item.get("relevance") not in RELEVANCE:
            raise ValueError("Décision Presse invalide ou hors candidats.")
        if item["relevance"] in {"DIRECT", "CONTEXTUAL"}:
            direct_or_contextual.add(item["url"])
    status = enrichment["status"]
    if status == "COMPLETED":
        if not source_urls or not source_urls <= direct_or_contextual:
            raise ValueError("COMPLETED exige des sources liées au signal.")
        citations = {int(value) for value in re.findall(r"\[(\d+)\]", enrichment["summary"])}
        if not citations or max(citations) > len(enrichment["sources"]):
            raise ValueError("La synthèse Presse doit renvoyer vers ses sources.")
    if status == "NO_EVIDENCE":
        if source_urls or candidates.get("errors"):
            raise ValueError("NO_EVIDENCE exige une collecte sans erreur et aucune source retenue.")
    if status == "UNRESOLVED" and not (candidates.get("errors") or any(item.get("relevance") == "AMBIGUOUS" for item in details["decisions"])):
        raise ValueError("UNRESOLVED doit conserver une cause d'incertitude.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--enrichment", type=Path, required=True)
    args = parser.parse_args()
    validate(
        json.loads(args.candidates.read_text(encoding="utf-8")),
        json.loads(args.enrichment.read_text(encoding="utf-8")),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
