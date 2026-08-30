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
class SearchCards(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.card_depth = 0
        self.current: dict[str, Any] | None = None
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.cards: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "div" and "recherche-card" in (attributes.get("class") or ""):
            self.card_depth = 1
            self.current = {"href": None, "title": None, "dates": []}
        elif tag == "div" and self.card_depth:
            self.card_depth += 1
        if tag == "a" and self.card_depth and self.current is not None and self.current.get("href") is None:
            self.current_href = attributes.get("href")
            self.current_text = []
        if tag == "time" and self.card_depth and self.current is not None:
            value = attributes.get("datetime")
            if value:
                self.current["dates"].append(value)

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_href is not None and self.current is not None:
            self.current["href"] = self.current_href
            self.current["title"] = " ".join(" ".join(self.current_text).split()) or None
            self.current_href = None
            self.current_text = []
        if tag == "div" and self.card_depth:
            self.card_depth -= 1
            if self.card_depth == 0 and self.current is not None:
                if self.current.get("href"):
                    self.cards.append(self.current)
                self.current = None


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
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Les cartes de recherche ont une structure HTML régulière mais des div imbriquées
    # variables ; les segments débutant par leur classe évitent les liens de navigation.
    for card in re.split(r"<div\s+class=['\"][^'\"]*recherche-card", page_html, flags=re.IGNORECASE)[1:]:
        link = re.search(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", card, flags=re.IGNORECASE | re.DOTALL)
        if link is None:
            continue
        url = urllib.parse.urljoin(page_url, html.unescape(link.group(1)))
        if url in seen:
            continue
        seen.add(url)
        title = " ".join(re.sub(r"<[^>]+>", " ", link.group(2)).split())
        dates = re.findall(r"<time\s+[^>]*datetime=['\"]([^'\"]+)['\"]", card, flags=re.IGNORECASE)
        records.append({
            "title": html.unescape(title) or None,
            "url": url,
            "dates": dates,
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
        url = search_url(page)
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
