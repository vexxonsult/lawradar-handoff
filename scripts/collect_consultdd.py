#!/usr/bin/env python3
"""Énumère les consultations récentes depuis la recherche officielle, sans interprétation."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from io import BytesIO
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
        classes = set((attributes.get("class") or "").split())
        if tag == "div" and "recherche-card" in classes:
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


def fetch_bytes(url: str, limit: int = 50_000_000) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "LawRadar-ConsultDD-Collector/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        size = int(response.headers.get("Content-Length") or 0)
        if size > limit:
            raise ValueError("PIECE_TROP_VOLUMINEUSE")
        payload = response.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("PIECE_TROP_VOLUMINEUSE")
        return payload


def clean_html(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def official_detail_from_html(page_html: str) -> dict[str, Any]:
    """Extrait la preuve affichée dans une page officielle de consultation."""
    title = re.search(r"<h1\b[^>]*>(.*?)</h1>", page_html, re.IGNORECASE | re.DOTALL)
    period = re.search(r"<div\s+class=['\"][^'\"]*date-article[^'\"]*['\"][^>]*>.*?<p>(.*?)</p>", page_html, re.IGNORECASE | re.DOTALL)
    content = re.search(r"<div\s+class=['\"][^'\"]*texte-article[^'\"]*['\"][^>]*>(.*?)</div>\s*<div\s+class=['\"]listedocuments", page_html, re.IGNORECASE | re.DOTALL)
    return {
        "official_title": clean_html(title.group(1)) if title else None,
        "official_period": clean_html(period.group(1)) if period else None,
        "official_text": (clean_html(content.group(1))[:12000] if content else None),
    }


def attachment_links_from_html(page_html: str, page_url: str) -> list[dict[str, str]]:
    links = []
    for href, label in re.findall(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", page_html, re.I | re.S):
        url = urllib.parse.urljoin(page_url, html.unescape(href))
        if "camino.beta.gouv.fr/apiUrl/download/" in url:
            links.append({"url": url, "label": clean_html(label)})
    return links


def financial_evidence_from_pdf(payload: bytes, url: str) -> list[dict[str, Any]]:
    from pypdf import PdfReader
    pattern = re.compile(r"redevance|garantie financi.re|cautionnement|montant.*(?:euro|EUR)|paiement", re.I)
    evidence = []
    for number, page in enumerate(PdfReader(BytesIO(payload)).pages, start=1):
        for line in (page.extract_text() or "").splitlines():
            if pattern.search(line):
                evidence.append({"source_url": url, "page": number, "excerpt": " ".join(line.split())})
    return evidence[:40]


def records_from_html(page_html: str, page_url: str) -> list[dict[str, Any]]:
    parser = SearchCards()
    parser.feed(page_html)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in parser.cards:
        href = card.get("href")
        if not isinstance(href, str):
            continue
        url = urllib.parse.urljoin(page_url, html.unescape(href))
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        title = card.get("title")
        dates = card.get("dates")
        # Les catégories, la pagination, l'abonnement et les documents bruts ne
        # sont pas des consultations à analyser. Leur passage au moteur créait
        # artificiellement des dettes UNRESOLVED.
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(dates, list)
            or not dates
            or parsed.path in {"", "/", "/spip.php"}
            or parsed.path.startswith("/IMG/")
            or "debut_listearticles" in query
            or query.get("page") == ["recherche"]
            or title.strip().casefold() == "consultations publiques"
        ):
            continue
        if url in seen:
            continue
        seen.add(url)
        records.append({
            "title": title,
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
                try:
                    detail_html = fetch_text(record["url"])
                    record["official_detail"] = official_detail_from_html(detail_html)
                    attachments = attachment_links_from_html(detail_html, record["url"])
                    record["official_attachments"] = attachments
                    record["financial_evidence"] = []
                    for attachment in attachments[:1]:
                        try:
                            record["financial_evidence"].extend(
                                financial_evidence_from_pdf(fetch_bytes(attachment["url"]), attachment["url"])
                            )
                        except Exception as exc:
                            record.setdefault("attachment_errors", []).append(type(exc).__name__)
                    record["detail_status"] = "PRIMARY_PAGE_READ"
                except Exception as exc:
                    record["official_detail"] = None
                    record["official_attachments"] = []
                    record["financial_evidence"] = []
                    record["detail_status"] = "PRIMARY_PAGE_UNAVAILABLE"
                    record["detail_error"] = type(exc).__name__
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
