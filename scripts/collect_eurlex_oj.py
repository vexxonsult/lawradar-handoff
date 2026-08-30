#!/usr/bin/env python3
"""Énumère les JO L depuis le graphe officiel Cellar, sans interprétation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"


def build_query(start_date: str, end_date: str) -> str:
    """Requête officielle Cellar : les métadonnées des éditions JO d'une période."""
    return f'''prefix cdm: <http://publications.europa.eu/ontology/cdm#>
prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
prefix xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?uri ?ojclass ?ojnumber ?ojcollection ?ojyear ?workdatedoc
WHERE {{
  ?uri cdm:official-journal_class ?ojclass .
  ?uri cdm:official-journal_number ?ojnumber .
  ?uri cdm:official-journal_part_of_collection_document ?ojcollection .
  ?uri cdm:official-journal_year ?ojyear .
  ?uri cdm:work_date_document ?workdatedoc .
  ?uri rdf:type cdm:official-journal .
  FILTER(?workdatedoc >= "{start_date}"^^xsd:date && ?workdatedoc <= "{end_date}"^^xsd:date)
}}
ORDER BY ?workdatedoc ?ojnumber'''


def fetch_json(endpoint: str, query: str) -> dict[str, Any]:
    encoded = urllib.parse.urlencode({"query": query, "format": "application/sparql-results+json"}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=encoded,
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "LawRadar-EUR-Lex-Collector/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def binding_value(binding: dict[str, Any], name: str) -> str | None:
    value = binding.get(name, {}).get("value")
    return value if isinstance(value, str) else None


def is_l_series(oj_class: str | None) -> bool:
    if not oj_class:
        return False
    return oj_class.rstrip("/#").rsplit("/", 1)[-1] == "L"


def records_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for binding in response.get("results", {}).get("bindings", []):
        oj_class = binding_value(binding, "ojclass")
        if not is_l_series(oj_class):
            continue
        records.append({
            "cellar_uri": binding_value(binding, "uri"),
            "official_journal_class": oj_class,
            "official_journal_number": binding_value(binding, "ojnumber"),
            "official_journal_collection": binding_value(binding, "ojcollection"),
            "official_journal_year": binding_value(binding, "ojyear"),
            "publication_date": binding_value(binding, "workdatedoc"),
            "interpretation": None,
        })
    return sorted(records, key=lambda item: (item["publication_date"] or "", item["official_journal_number"] or "", item["cellar_uri"] or ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--from", dest="start_date")
    parser.add_argument("--to", dest="end_date")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--endpoint", default=ENDPOINT)
    args = parser.parse_args()
    if args.days < 1:
        raise RuntimeError("--days doit être supérieur ou égal à 1.")
    if bool(args.start_date) != bool(args.end_date):
        raise RuntimeError("--from et --to doivent être fournis ensemble.")
    if args.start_date:
        start_date, end_date = args.start_date, args.end_date
    else:
        end = dt.datetime.now(dt.timezone.utc).date()
        start = end - dt.timedelta(days=args.days - 1)
        start_date, end_date = start.isoformat(), end.isoformat()

    query = build_query(start_date, end_date)
    response = fetch_json(args.endpoint, query)
    payload = {
        "schema": "lawradar-primary-eurlex-oj-v1",
        "status": "PRIMARY_INDEX_READ",
        "source_kind": "PRIMARY_OPEN_DATA",
        "source_publisher": "Publications Office of the European Union (Cellar)",
        "endpoint": args.endpoint,
        "coverage_start": start_date,
        "coverage_end": end_date,
        "query": query,
        "documents": records_from_response(response),
        "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "interpretation": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"documents": len(payload["documents"]), "coverage_start": start_date, "coverage_end": end_date}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COLLECTOR_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
