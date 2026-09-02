#!/usr/bin/env python3
"""Collecte BOAMP déterministe et bornée pour un fait d'opportunité courant.

Cette couche n'appelle aucun modèle et ne modifie jamais le Radar. Elle ne lit
que des champs BOAMP publics et compacts : objet, dates, acheteur, nature et
lien vers l'avis. Le jeu BOAMP ne fournit pas un montant structuré fiable ; le
collecteur le représente donc explicitement par ``null`` plutôt que de tenter
d'extraire un montant depuis le texte intégral d'un avis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SELECT_FIELDS = "idweb,objet,dateparution,datelimitereponse,nomacheteur,nature,nature_libelle,etat,url_avis"
STOPWORDS = {
    "avec", "dans", "pour", "plus", "moins", "entreprise", "entreprises",
    "nouveau", "nouvelle", "obligation", "obligations", "france", "toutes",
}


def facts_hash(facts: dict[str, Any]) -> str:
    raw = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def clean_query(value: str) -> str | None:
    value = " ".join(value.split()).strip()
    if not value:
        return None
    words = [word for word in re.findall(r"[\wÀ-ÿ'-]+", value) if len(text_key(word)) >= 3]
    meaningful = [word for word in words if text_key(word) not in STOPWORDS]
    if not meaningful:
        return None
    return " ".join(meaningful[:10])[:120]


def build_queries(facts: dict[str, Any], maximum: int) -> list[str]:
    """Build queries from current facts only; historical runs are never read."""
    legal = facts.get("legal", {}) if isinstance(facts.get("legal"), dict) else {}
    requirements = facts.get("requirements", {}) if isinstance(facts.get("requirements"), dict) else {}
    candidates: list[str] = []
    for value in (
        facts.get("keywords"), facts.get("affected_scope"), legal.get("affected_scope"),
        requirements.get("affected_scope"), facts.get("title"), legal.get("title"),
    ):
        candidates.extend(strings(value))
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        query = clean_query(candidate)
        if not query or text_key(query) in seen:
            continue
        seen.add(text_key(query))
        queries.append(query)
        if len(queries) >= maximum:
            break
    return queries


def escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def api_where(search_field: str, query: str) -> str:
    return f'search({search_field}, "{escape_literal(query)}")'


def http_json(endpoint: str, params: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = Request(
        f"{endpoint}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "LawRadar-BOAMP/0.1"},
    )
    with urlopen(request, timeout=timeout) as response:  # nosec B310: endpoint is versioned configuration
        body = response.read().decode("utf-8").strip()
    if not body:
        raise ValueError("Réponse BOAMP vide.")
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Réponse BOAMP invalide.")
    return payload


def parse_deadline(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def notice_kind(record: dict[str, Any]) -> str:
    nature = " ".join(str(record.get(key) or "") for key in ("nature", "nature_libelle")).upper()
    normalized = text_key(nature)
    if "pre information" in normalized or "preinformation" in normalized:
        return "PRE_INFORMATION"
    if "ATTRIBUT" in nature or "RESULTAT" in nature:
        return "AWARD"
    if "APPEL" in nature or "MARCH" in nature or "CONCESS" in nature:
        return "TENDER"
    return "OTHER"


def compact_record(record: dict[str, Any]) -> dict[str, Any] | None:
    identifier = record.get("idweb")
    title = record.get("objet")
    if not isinstance(identifier, str) or not identifier or not isinstance(title, str) or not title.strip():
        return None
    return {
        "id": identifier,
        "title": " ".join(title.split()),
        "buyer": record.get("nomacheteur") if isinstance(record.get("nomacheteur"), str) else None,
        "published_at": record.get("dateparution") if isinstance(record.get("dateparution"), str) else None,
        "response_deadline": record.get("datelimitereponse") if isinstance(record.get("datelimitereponse"), str) else None,
        "notice_kind": notice_kind(record),
        "notice_state": record.get("etat") if isinstance(record.get("etat"), str) else None,
        "url": record.get("url_avis") if isinstance(record.get("url_avis"), str) else None,
        "amount_eur": None,
    }


def summarize(records: list[dict[str, Any]], current: datetime) -> dict[str, Any]:
    tenders = [item for item in records if item["notice_kind"] == "TENDER"]
    awards = [item for item in records if item["notice_kind"] == "AWARD"]
    active = [item for item in tenders if (deadline := parse_deadline(item["response_deadline"])) and deadline >= current]
    buyers = Counter(item["buyer"] for item in records if item.get("buyer"))
    return {
        "notices_observed": len(records),
        "tender_notices_observed": len(tenders),
        "open_tenders_observed": len(active),
        "tender_notices_without_deadline": sum(1 for item in tenders if item["response_deadline"] is None),
        "award_notices_observed": len(awards),
        "amounts": {
            "known_total_eur": None,
            "reason": "Le jeu BOAMP structuré interrogé ne publie pas de montant d'avis exploitable sans analyser le texte intégral, ce que ce collecteur ne fait pas.",
        },
        "principal_buyers": [{"name": name, "notices": count} for name, count in buyers.most_common(5)],
    }


def validate_inputs(facts: dict[str, Any], config: dict[str, Any]) -> None:
    if facts.get("schema") != "lawradar-opportunity-facts-v1":
        raise ValueError("Faits d'opportunité non pris en charge.")
    if not isinstance(facts.get("signal_id"), str) or not facts["signal_id"]:
        raise ValueError("signal_id absent des faits d'opportunité.")
    if config.get("schema") != "lawradar-boamp-collector-config-v1":
        raise ValueError("Configuration BOAMP non prise en charge.")
    if config.get("activation") != "manual_only":
        raise ValueError("Le collecteur BOAMP doit rester en activation manuelle.")
    if not isinstance(config.get("endpoint"), str) or not config["endpoint"].startswith("https://"):
        raise ValueError("Endpoint BOAMP invalide.")
    if config.get("search_field") != "objet":
        raise ValueError("Seul le champ BOAMP 'objet' est autorisé pour la V0.")
    limits = config.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("Limites BOAMP absentes.")
    for key in ("max_queries_per_signal", "page_size", "max_pages_per_query", "max_records_in_output", "attempts_per_request", "timeout_seconds"):
        if not isinstance(limits.get(key), int) or limits[key] < 1:
            raise ValueError(f"Limite BOAMP invalide : {key}.")
    if not isinstance(limits.get("minimum_interval_seconds"), (int, float)) or limits["minimum_interval_seconds"] < 0:
        raise ValueError("Intervalle BOAMP invalide.")


def collect(
    facts: dict[str, Any], config: dict[str, Any], now: datetime | None = None,
    fetch: Callable[[str, dict[str, Any], int], dict[str, Any]] = http_json,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    validate_inputs(facts, config)
    limits = config["limits"]
    current = now or datetime.now(UTC)
    queries = build_queries(facts, limits["max_queries_per_signal"])
    if not queries:
        raise ValueError("Aucun mot-clé ni périmètre affecté exploitable dans les faits d'opportunité.")

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    errors: list[dict[str, Any]] = []
    query_log: list[dict[str, Any]] = []
    successful_queries = 0
    request_count = 0
    for query in queries:
        pages_succeeded = 0
        records_received = 0
        total_reported: int | None = None
        query_failed = False
        for page in range(limits["max_pages_per_query"]):
            if request_count:
                sleep(float(limits["minimum_interval_seconds"]))
            params = {
                "select": SELECT_FIELDS,
                "where": api_where(config["search_field"], query),
                "order_by": "dateparution desc",
                "limit": limits["page_size"],
                "offset": page * limits["page_size"],
            }
            payload: dict[str, Any] | None = None
            failure: Exception | None = None
            for attempt in range(limits["attempts_per_request"]):
                request_count += 1
                try:
                    payload = fetch(config["endpoint"], params, limits["timeout_seconds"])
                    break
                except Exception as caught:
                    failure = caught
                    if attempt + 1 < limits["attempts_per_request"]:
                        sleep(float(limits["minimum_interval_seconds"]))
            if payload is None:
                query_failed = True
                errors.append({"query": query, "page": page + 1, "error": str(failure or "Erreur BOAMP inconnue.")})
                break
            raw_records = payload["results"]
            total = payload.get("total_count")
            total_reported = total if isinstance(total, int) else total_reported
            pages_succeeded += 1
            records_received += len(raw_records)
            for raw in raw_records:
                if not isinstance(raw, dict):
                    continue
                compact = compact_record(raw)
                if not compact or compact["id"] in seen:
                    continue
                seen.add(compact["id"])
                if len(records) < limits["max_records_in_output"]:
                    records.append(compact)
            if len(raw_records) < limits["page_size"] or len(records) >= limits["max_records_in_output"]:
                break
        if pages_succeeded:
            successful_queries += 1
        query_log.append({
            "query": query,
            "pages_succeeded": pages_succeeded,
            "records_received": records_received,
            "total_reported": total_reported,
            "status": "UNRESOLVED" if query_failed else "COMPLETED",
        })

    status = "UNRESOLVED" if successful_queries == 0 else ("COMPLETED" if records else "NO_EVIDENCE")
    return {
        "schema": "lawradar-market-demand-boamp-v1",
        "signal_id": facts["signal_id"],
        "signal_hash": facts_hash(facts),
        "collected_at_utc": current.isoformat(),
        "collection_status": status,
        "source": {"name": "BOAMP", "dataset": config["dataset"], "endpoint": config["endpoint"]},
        "queries": query_log,
        "request_count": request_count,
        "summary": summarize(records, current),
        "observations": records,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True, help="Fichier lawradar-opportunity-facts-v1")
    parser.add_argument("--config", type=Path, default=Path("config/boamp-collector-config-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("out/market-demand-boamp.json"))
    args = parser.parse_args()
    result = collect(
        json.loads(args.facts.read_text(encoding="utf-8")),
        json.loads(args.config.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
