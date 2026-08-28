#!/usr/bin/env python3
"""Collecte DILA JORF : preuve brute, sans qualification ni interprétation."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

INDEX_URL = "http://echanges.dila.gouv.fr/OPENDATA/JORF/"
ARCHIVE_RE = re.compile(r"^JORF_(\d{8})-(\d{6})\.tar\.gz$")
ID_RE = re.compile(r"^(JORFTEXT\d+)\.xml$")
ARTICLE_RE = re.compile(r"^(JORFARTI\d+)\.xml$")


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def fetch(url: str, destination: Path | None = None) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": "LawRadar-DILA-Collector/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        if destination is None:
            return response.read()
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return None


def available_archives(index_url: str) -> list[tuple[str, str, str]]:
    parser = _Links()
    parser.feed((fetch(index_url) or b"").decode("utf-8", errors="replace"))
    archives = []
    for href in parser.links:
        name = href.rsplit("/", 1)[-1]
        match = ARCHIVE_RE.fullmatch(name)
        if match:
            archives.append((match.group(1), match.group(2), name))
    return sorted(set(archives))


def choose_archive(archives: list[tuple[str, str, str]], requested_date: str | None) -> tuple[str, str, str]:
    if requested_date:
        wanted = requested_date.replace("-", "")
        candidates = [item for item in archives if item[0] == wanted]
    else:
        candidates = archives
    if not candidates:
        label = requested_date or "la dernière date disponible"
        raise RuntimeError(f"Aucune archive DILA disponible pour {label}.")
    # Plusieurs livraisons existent certains jours : la plus tardive est la plus complète.
    return max(candidates)


def xml_root(handle: tarfile.TarFile, member: tarfile.TarInfo) -> ET.Element:
    stream = handle.extractfile(member)
    if stream is None:
        raise RuntimeError(f"Lecture impossible : {member.name}")
    return ET.fromstring(stream.read())


def value(root: ET.Element, path: str) -> str | None:
    node = root.find(path)
    if node is None or node.text is None:
        return None
    text = " ".join(node.text.split())
    return text or None


def text_payload(root: ET.Element) -> str:
    content = root.find(".//BLOC_TEXTUEL/CONTENU")
    if content is None:
        return ""
    return "\n".join(part.strip() for part in content.itertext() if part.strip())


def version_payload(root: ET.Element) -> str:
    """Transcription mécanique d'un TEXTE_VERSION sans mélanger ses métadonnées."""
    sections = ("NOTICE", "VISAS", "TP", "ABRO", "RECT", "SM")
    chunks = []
    for section in sections:
        node = root.find(section)
        if node is not None:
            chunks.extend(part.strip() for part in node.itertext() if part.strip())
    return "\n".join(chunks)


def evidence_from_archive(archive: Path, archive_url: str, targets: set[str], out: Path) -> dict[str, Any]:
    sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    with tarfile.open(archive, "r:gz") as handle:
        members = [member for member in handle.getmembers() if member.isfile() and member.name.endswith(".xml")]
        text_members: dict[str, tarfile.TarInfo] = {}
        article_members: dict[str, tarfile.TarInfo] = {}
        for member in members:
            basename = Path(member.name).name
            text_match = ID_RE.fullmatch(basename)
            article_match = ARTICLE_RE.fullmatch(basename)
            if text_match:
                text_members[text_match.group(1)] = member
            elif article_match:
                article_members[article_match.group(1)] = member

        documents: list[dict[str, Any]] = []
        for identifier in sorted(targets & text_members.keys()):
            root = xml_root(handle, text_members[identifier])
            article_ids = [node.attrib["id"] for node in root.findall(".//LIEN_ART") if node.attrib.get("id") in article_members]
            article_roots = [xml_root(handle, article_members[article_id]) for article_id in dict.fromkeys(article_ids)]
            title = next((value(article, ".//CONTEXTE/TEXTE/TITRE_TXT") for article in article_roots if value(article, ".//CONTEXTE/TEXTE/TITRE_TXT")), None)
            if title is None:
                title = value(root, ".//META_TEXTE_VERSION/TITREFULL") or value(root, ".//META_TEXTE_VERSION/TITRE")
            articles = [{"article_id": article_id, "xml_source": ET.tostring(article, encoding="unicode"), "plain_text": text_payload(article)} for article_id, article in zip(article_ids, article_roots)]
            if not articles:
                articles = [{"article_id": None, "xml_source": None, "plain_text": version_payload(root)}]
            payload = {
                "schema": "lawradar-primary-evidence-v1",
                "source_kind": "PRIMARY_OPEN_DATA",
                "source_publisher": "Direction de l'information légale et administrative (DILA)",
                "archive_url": archive_url,
                "archive_sha256": sha256,
                "text_id": identifier,
                "nature": value(root, ".//META_COMMUN/NATURE"),
                "nor": value(root, ".//META_TEXTE_CHRONICLE/NOR"),
                "publication_date": value(root, ".//META_TEXTE_CHRONICLE/DATE_PUBLI"),
                "journal_number": value(root, ".//META_TEXTE_CHRONICLE/NUM_PARUTION"),
                "title": title,
                "article_ids": article_ids,
                "xml_source": ET.tostring(root, encoding="unicode"),
                "articles": articles,
                "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "interpretation": None,
            }
            documents.append(payload)

    out.mkdir(parents=True, exist_ok=True)
    document_dir = out / "documents"
    document_dir.mkdir(exist_ok=True)
    for document in documents:
        (document_dir / f"{document['text_id']}.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema": "lawradar-primary-manifest-v1",
        "status": "PRIMARY_ARCHIVE_READ",
        "source_publisher": "Direction de l'information légale et administrative (DILA)",
        "archive_url": archive_url,
        "archive_filename": archive.name,
        "archive_sha256": sha256,
        "archive_size_bytes": archive.stat().st_size,
        "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_count": len(targets),
        "documents_found": [document["text_id"] for document in documents],
        "documents_missing_from_this_archive": sorted(targets - {document["text_id"] for document in documents}),
        "interpretation": None,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--date", help="Date de publication AAAA-MM-JJ ; par défaut, dernière archive disponible.")
    parser.add_argument("--index-url", default=INDEX_URL)
    args = parser.parse_args()
    targets_data = json.loads(args.targets.read_text(encoding="utf-8"))
    targets = set(targets_data["targets"])
    if not all(re.fullmatch(r"JORFTEXT\d+", item) for item in targets):
        raise RuntimeError("La liste de cibles contient un identifiant JORFTEXT invalide.")

    date, time, filename = choose_archive(available_archives(args.index_url), args.date)
    archive_url = args.index_url.rstrip("/") + "/" + filename
    with tempfile.TemporaryDirectory(prefix="lawradar-dila-") as temporary:
        archive = Path(temporary) / filename
        fetch(archive_url, archive)
        if not tarfile.is_tarfile(archive):
            raise RuntimeError("L'archive DILA téléchargée n'est pas une archive TAR lisible.")
        manifest = evidence_from_archive(archive, archive_url, targets, args.out)
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COLLECTOR_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
