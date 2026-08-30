#!/usr/bin/env python3
"""Énumère les actes JO L via la vue quotidienne officielle EUR-Lex, sans interprétation."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

DAILY_VIEW_URL = "https://eur-lex.europa.eu/oj/daily-view/L-series/default.html"


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_href is not None:
            self.links.append((self.current_href, " ".join(" ".join(self.current_text).split())))
            self.current_href = None
            self.current_text = []


def daily_view_url(date: dt.date) -> str:
    query = urllib.parse.urlencode({"ojDate": date.strftime("%d%m%Y"), "locale": "en"})
    return DAILY_VIEW_URL + "?" + query


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "LawRadar-EUR-Lex-Collector/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", errors="replace")


def records_from_html(page_html: str, page_url: str, publication_date: str) -> list[dict[str, Any]]:
    parser = Links()
    parser.feed(page_html)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href, title in parser.links:
        url = urllib.parse.urljoin(page_url, html.unescape(href))
        uri = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("uri", [None])[0]
        if not isinstance(uri, str) or not uri.startswith("OJ:L_") or url in seen:
            continue
        seen.add(url)
        records.append({
            "official_journal_id": uri,
            "publication_date": publication_date,
            "title": html.unescape(title) or None,
            "url": url,
            "interpretation": None,
        })
    return records


def date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=offset) for offset in range((end - start).days + 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--from", dest="start_date")
    parser.add_argument("--to", dest="end_date")
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    if args.days < 1:
        raise RuntimeError("--days doit être supérieur ou égal à 1.")
    if bool(args.start_date) != bool(args.end_date):
        raise RuntimeError("--from et --to doivent être fournis ensemble.")
    if args.start_date:
        start, end = dt.date.fromisoformat(args.start_date), dt.date.fromisoformat(args.end_date)
    else:
        end = dt.datetime.now(dt.timezone.utc).date()
        start = end - dt.timedelta(days=args.days - 1)
    if start > end:
        raise RuntimeError("--from doit précéder --to.")

    documents: list[dict[str, Any]] = []
    daily_views: list[str] = []
    for date in date_range(start, end):
        url = daily_view_url(date)
        daily_views.append(url)
        documents.extend(records_from_html(fetch_text(url), url, date.isoformat()))

    payload = {
        "schema": "lawradar-primary-eurlex-oj-v2",
        "status": "PRIMARY_INDEX_READ",
        "source_kind": "PRIMARY_OPEN_DATA",
        "source_publisher": "Publications Office of the European Union (EUR-Lex)",
        "source_route": "Official Journal L series daily view",
        "coverage_start": start.isoformat(),
        "coverage_end": end.isoformat(),
        "daily_views": daily_views,
        "documents": documents,
        "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "interpretation": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"documents": len(documents), "days_read": len(daily_views), "coverage_start": start.isoformat(), "coverage_end": end.isoformat()}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COLLECTOR_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
