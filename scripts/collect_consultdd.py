#!/usr/bin/env python3
"""Énumère les consultations récentes depuis la recherche officielle, sans interprétation."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

BASE_URL = "https://www.consultations-publiques.developpement-durable.gouv.fr/"
ARTICLE_RE = re.compile(r"(?:^|/)[^?#]*-a(\d+)\.html(?:[?#].*)?$")


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.heading_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h2", "h3"}:
            self.heading_depth += 1
        if tag == "a":
            self.current_href = dict(attrs).get("href") if self.heading_depth else None
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_href is not None:
            self.links.append((self.current_href, " ".join(" ".join(self.current_text).split())))
            self.current_href = None
            self.current_text = []
        if tag in {"h2", "h3"}:
            self.heading_depth = max(0, self.heading_depth - 1)


def search_url(offset: int) -> str:
    query = urllib.parse.urlencode({
        "f_date": "0",
        "f_net": "0",
        "page": "recherche",
        "perimetre": "site",
        "r_start": str(offset),
        "recherche": "consultation",
        "tri": "datedesc",
        "typedoc": "",
        "lang": "fr",
    })
    return BASE_URL + "?" + query


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "LawRadar-ConsultDD-Collector/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", errors="replace")


def records_from_html(page_html: str, page_url: str) -> list[dict[str, Any]]:
    parser = Links()
    parser.feed(page_html)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href, title in parser.links:
        url = urllib.parse.urljoin(page_url, html.unescape(href))
        match = ARTICLE_RE.search(url)
        if not match or url in seen:
            continue
        seen.add(url)
        records.append({
            "consultation_id": f"a{match.group(1)}",
            "title": html.unescape(title) or None,
            "url": url,
            "interpretation": None,
        })
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pages", type=int, default=5, help="Nombre de pages récentes à lire (10 résultats par page).")
    args = parser.parse_args()
    if args.pages < 1:
        raise RuntimeError("--pages doit être supérieur ou égal à 1.")

    documents: list[dict[str, Any]] = []
    queries = []
    seen: set[str] = set()
    for page in range(args.pages):
        url = search_url(page * 10)
        page_records = records_from_html(fetch_text(url), url)
        queries.append(url)
        for record in page_records:
            if record["url"] not in seen:
                seen.add(record["url"])
                documents.append(record)
        if not page_records:
            break

    payload = {
        "schema": "lawradar-primary-consultdd-index-v1",
        "status": "PRIMARY_INDEX_READ",
        "source_kind": "PRIMARY_OPEN_DATA",
        "source_publisher": "Ministères de la Transition écologique, de l’Aménagement du territoire, des Transports, de la Ville et du Logement",
        "scope": "Les résultats les plus récents de la recherche officielle « consultation », relus chaque jour.",
        "queries": queries,
        "documents": documents,
        "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "interpretation": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"documents": len(documents), "pages_read": len(queries)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COLLECTOR_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
