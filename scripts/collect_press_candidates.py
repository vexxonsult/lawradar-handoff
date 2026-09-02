#!/usr/bin/env python3
"""Collecte des titres de presse pour un unique signal Radar retenu."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


def signal_hash(signal: dict[str, Any]) -> str:
    raw = json.dumps(signal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_retained_signal(dossier: dict[str, Any], requested_id: str) -> dict[str, Any]:
    if dossier.get("schema") != "lawradar-universal-signal-v1":
        raise ValueError("Dossier universel non pris en charge.")
    matches = [item for item in dossier.get("signals", []) if item.get("id") == requested_id]
    if len(matches) != 1:
        raise ValueError("Signal Presse absent ou dupliqué.")
    if matches[0].get("radar", {}).get("status") != "RETAINED":
        raise ValueError("L'agent Presse ne traite que les signaux RETAINED.")
    return matches[0]


def text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()


def canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    kept = [
        (key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid"}
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https" if parsed.scheme == "http" else parsed.scheme, parsed.netloc.lower(), path, urlencode(kept), ""))


def evidence_titles(signal: dict[str, Any]) -> list[str]:
    evidence = signal.get("source", {}).get("evidence", {})
    official = evidence.get("official", {}) if isinstance(evidence, dict) else {}
    candidates = [official.get("title"), evidence.get("title")]
    titles: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.split()).strip()
        key = text_key(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            titles.append(cleaned[:220])
    return titles


def build_queries(signal: dict[str, Any], limit: int) -> list[str]:
    queries = [f'"{title}" sourcelang:french' for title in evidence_titles(signal)]
    return queries[:limit]


def gdelt_articles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    articles = payload.get("articles", [])
    return articles if isinstance(articles, list) else []


def normalize_article(article: dict[str, Any]) -> dict[str, Any] | None:
    url = article.get("url")
    title = article.get("title")
    if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
        return None
    canonical = canonical_url(url)
    return {
        "url": canonical,
        "outlet": article.get("domain") or urlsplit(canonical).netloc,
        "published_at": article.get("seendate"),
        "title": " ".join(title.split()),
        "excerpt": None,
        "source": "gdelt-doc-2.0",
    }


def deduplicate(articles: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for article in articles:
        url = article["url"]
        title = text_key(article["title"])
        if url in seen_urls or title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        kept.append(article)
        if len(kept) >= maximum:
            break
    return kept


def http_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    request = Request(f"{url}?{urlencode(params)}", headers={"User-Agent": "LawRadar-Press/0.1"})
    with urlopen(request, timeout=20) as response:  # nosec B310: endpoint is configuration-controlled
        return json.loads(response.read().decode("utf-8"))


def collect(
    dossier: dict[str, Any], config: dict[str, Any], signal_id: str,
    now: datetime | None = None, fetch: Callable[[str, dict[str, Any]], dict[str, Any]] = http_json,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if config.get("schema") != "lawradar-press-agent-config-v1":
        raise ValueError("Configuration Presse non prise en charge.")
    signal = select_retained_signal(dossier, signal_id)
    limits = config.get("limits", {})
    source = config.get("sources", {}).get("gdelt_doc", {})
    if not source.get("enabled"):
        raise ValueError("La source GDELT n'est pas activée dans la configuration.")
    current = now or datetime.now(UTC)
    before = int(config.get("window_days_before", 14))
    queries = build_queries(signal, int(limits.get("max_queries_per_signal", 2)))
    maximum = int(limits.get("max_candidates_per_signal", 15))
    gathered: list[dict[str, Any]] = []
    query_log: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for index, query in enumerate(queries):
        if index:
            sleep(float(source.get("minimum_interval_seconds", 5)))
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": int(source.get("max_records_per_query", 10)),
            "startdatetime": (current - timedelta(days=before)).strftime("%Y%m%d%H%M%S"),
            "enddatetime": current.strftime("%Y%m%d%H%M%S"),
        }
        try:
            items = gdelt_articles(fetch(str(source["endpoint"]), params))
        except Exception as error:  # Source failure must be explicit, never become NO_EVIDENCE.
            errors.append({"source": "gdelt-doc-2.0", "query": query, "error": str(error)})
            query_log.append({"source": "gdelt-doc-2.0", "query": query, "hits": None})
            continue
        normalized = [item for article in items if (item := normalize_article(article)) is not None]
        gathered.extend(normalized)
        query_log.append({"source": "gdelt-doc-2.0", "query": query, "hits": len(normalized)})
    candidates = deduplicate(gathered, maximum)
    return {
        "schema": "lawradar-press-candidates-v1",
        "signal_id": signal_id,
        "signal_hash": signal_hash(signal),
        "observed_at_utc": current.isoformat(),
        "window": {
            "from": (current - timedelta(days=before)).date().isoformat(),
            "to": current.date().isoformat(),
        },
        "queries": query_log,
        "candidates_total": len(gathered),
        "candidates_after_dedup": len(candidates),
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(
        json.loads(args.dossier.read_text(encoding="utf-8")),
        json.loads(args.config.read_text(encoding="utf-8")),
        args.signal_id,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
