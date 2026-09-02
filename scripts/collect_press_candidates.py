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
from xml.etree import ElementTree


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
        if cleaned.endswith("..."):
            continue
        key = text_key(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            titles.append(cleaned[:220])
    return titles


def build_queries(signal: dict[str, Any], limit: int) -> list[str]:
    titles = evidence_titles(signal)
    if not titles:
        return []
    exact = titles[0].replace('"', " ")
    terms = [word for word in re.findall(r"[\wÀ-ÿ-]+", exact) if len(word) >= 4]
    stopwords = {"arrete", "relatif", "publique", "demande", "prolongation", "pour", "dans", "avec", "seine", "marne"}
    focused = [word for word in terms if text_key(word) not in stopwords][:7]
    queries = [f'"{exact}" sourcelang:french']
    if focused:
        queries.append(" ".join(focused) + " sourcelang:french")
    return queries[:limit]


def build_news_queries(signal: dict[str, Any], limit: int) -> list[str]:
    """Queries for a news RSS endpoint; no provider-specific operators leak in."""
    titles = evidence_titles(signal)
    if not titles:
        return []
    exact = titles[0].replace('"', " ")
    focused = sorted(distinctive_terms(signal))[:7]
    queries = [f'"{exact}"']
    if focused:
        queries.append(" ".join(focused))
    return queries[:limit]


STOPWORDS = {
    "arrete", "relatif", "publique", "demande", "prolongation", "pour", "dans", "avec",
    "seine", "marne", "consultation", "public", "permis", "decret", "projet", "titre",
    "partir", "objet", "concernant", "nouveau", "nouvelle",
}


def distinctive_terms(signal: dict[str, Any]) -> set[str]:
    """Terms derived from the current signal only, never from previous runs."""
    terms: set[str] = set()
    for title in evidence_titles(signal):
        for word in re.findall(r"[\wÀ-ÿ-]+", text_key(title)):
            if len(word) >= 4 and word not in STOPWORDS:
                terms.add(word)
    return terms


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
        body = response.read().decode("utf-8").strip()
    if not body:
        raise ValueError("Réponse GDELT vide.")
    return json.loads(body)


def http_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "LawRadar-Press/0.1"})
    with urlopen(request, timeout=20) as response:  # nosec B310: endpoint is configuration-controlled
        body = response.read().decode("utf-8").strip()
    if not body:
        raise ValueError("Flux RSS vide.")
    return body


def xml_text(node: ElementTree.Element, name: str) -> str | None:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] == name and child.text:
            value = " ".join(child.text.split())
            if value:
                return value
    return None


def rss_link(node: ElementTree.Element) -> str | None:
    direct = xml_text(node, "link")
    if direct and direct.startswith(("http://", "https://")):
        return direct
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] != "link":
            continue
        href = child.attrib.get("href")
        if href and href.startswith(("http://", "https://")):
            return href
    return None


def strip_excerpt(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    words = " ".join(text.split()).split()
    return " ".join(words[:25]) or None


def rss_articles(feed: dict[str, Any], body: str, signal: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse titles and excerpts only; article bodies are never requested."""
    root = ElementTree.fromstring(body)
    terms = distinctive_terms(signal)
    minimum = max(1, int(feed.get("minimum_matching_terms", 2)))
    items = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
    results: list[dict[str, Any]] = []
    for item in items:
        title = xml_text(item, "title")
        url = rss_link(item)
        if not title or not url:
            continue
        excerpt = strip_excerpt(xml_text(item, "description") or xml_text(item, "summary") or xml_text(item, "content"))
        searchable = text_key(f"{title} {excerpt or ''}")
        matched = sorted(term for term in terms if term in searchable.split())
        if len(matched) < minimum:
            continue
        canonical = canonical_url(url)
        results.append({
            "url": canonical,
            "outlet": xml_text(item, "source") or feed["outlet"],
            "published_at": xml_text(item, "pubDate") or xml_text(item, "published") or xml_text(item, "updated"),
            "title": " ".join(title.split()),
            "excerpt": excerpt,
            "source": f"publisher-rss:{feed['id']}",
            "source_kind": feed.get("source_kind", "editorial"),
            "matched_terms": matched,
        })
    return results


def collect(
    dossier: dict[str, Any], config: dict[str, Any], signal_id: str,
    now: datetime | None = None, fetch: Callable[[str, dict[str, Any]], dict[str, Any]] = http_json,
    fetch_text: Callable[[str], str] = http_text,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if config.get("schema") != "lawradar-press-agent-config-v1":
        raise ValueError("Configuration Presse non prise en charge.")
    signal = select_retained_signal(dossier, signal_id)
    limits = config.get("limits", {})
    sources = config.get("sources", {})
    source = sources.get("gdelt_doc", {})
    news = sources.get("google_news_rss", {})
    feeds = [item for item in sources.get("publisher_rss", []) if isinstance(item, dict) and item.get("enabled")]
    if not source.get("enabled") and not news.get("enabled") and not feeds:
        raise ValueError("Aucune source Presse n'est activée dans la configuration.")
    current = now or datetime.now(UTC)
    before = int(config.get("window_days_before", 14))
    queries = build_queries(signal, int(limits.get("max_queries_per_signal", 2)))
    if not queries:
        raise ValueError("Le signal ne contient aucun intitulé exploitable pour la recherche Presse.")
    maximum = int(limits.get("max_candidates_per_signal", 15))
    gathered: list[dict[str, Any]] = []
    query_log: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    required_errors: list[dict[str, str]] = []
    source_statuses: list[dict[str, Any]] = []
    if source.get("enabled"):
        gdelt_failed = False
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
            attempts = max(1, int(source.get("attempts_per_query", 1)))
            error: Exception | None = None
            items: list[dict[str, Any]] = []
            for attempt in range(attempts):
                try:
                    items = gdelt_articles(fetch(str(source["endpoint"]), params))
                    error = None
                    break
                except Exception as caught:  # Source failure must be explicit, never become NO_EVIDENCE.
                    error = caught
                    if attempt + 1 < attempts:
                        sleep(float(source.get("retry_delay_seconds", 3)))
            if error is not None:
                entry = {"source": "gdelt-doc-2.0", "query": query, "error": str(error)}
                errors.append(entry)
                if source.get("required", True):
                    required_errors.append(entry)
                gdelt_failed = True
                query_log.append({"source": "gdelt-doc-2.0", "query": query, "hits": None})
                continue
            normalized = [item for article in items if (item := normalize_article(article)) is not None]
            gathered.extend(normalized)
            query_log.append({"source": "gdelt-doc-2.0", "query": query, "hits": len(normalized)})
        source_statuses.append({"source": "gdelt-doc-2.0", "required": source.get("required", True), "success": not gdelt_failed})
    if news.get("enabled"):
        news_failed = False
        news_feed = {
            "id": "google-news-fr",
            "outlet": "Google News",
            "source_kind": "news_aggregator",
            "minimum_matching_terms": int(news.get("minimum_matching_terms", 1)),
        }
        for query in build_news_queries(signal, int(limits.get("max_queries_per_signal", 2))):
            params = {
                "q": query,
                "hl": news.get("language", "fr"),
                "gl": news.get("country", "FR"),
                "ceid": news.get("edition", "FR:fr"),
            }
            try:
                endpoint = f"{news['endpoint']}?{urlencode(params)}"
                items = rss_articles(news_feed, fetch_text(endpoint), signal)
                gathered.extend(items)
                query_log.append({"source": "google-news-rss", "query": query, "hits": len(items)})
            except Exception as caught:
                entry = {"source": "google-news-rss", "query": query, "error": str(caught)}
                errors.append(entry)
                if news.get("required", False):
                    required_errors.append(entry)
                news_failed = True
                query_log.append({"source": "google-news-rss", "query": query, "hits": None})
        source_statuses.append({"source": "google-news-rss", "required": news.get("required", False), "success": not news_failed})
    for feed in feeds:
        feed_name = f"publisher-rss:{feed.get('id', 'unknown')}"
        try:
            items = rss_articles(feed, fetch_text(str(feed["url"])), signal)
            gathered.extend(items)
            query_log.append({"source": feed_name, "query": "signal-term-match", "hits": len(items)})
            source_statuses.append({"source": feed_name, "required": feed.get("required", True), "success": True})
        except Exception as caught:
            entry = {"source": feed_name, "query": "rss", "error": str(caught)}
            errors.append(entry)
            if feed.get("required", True):
                required_errors.append(entry)
            query_log.append({"source": feed_name, "query": "rss", "hits": None})
            source_statuses.append({"source": feed_name, "required": feed.get("required", True), "success": False})
    candidates = deduplicate(gathered, maximum)
    successful_sources = [item for item in source_statuses if item["success"]]
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
        "required_errors": required_errors,
        "source_statuses": source_statuses,
        "collection_successful": bool(successful_sources) and not required_errors,
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
