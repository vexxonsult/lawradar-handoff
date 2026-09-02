#!/usr/bin/env python3
"""Ajoute des extraits officiels bornés aux candidats JORF du moteur.

La source reste l'archive ouverte DILA déjà utilisée par le collecteur. Cette
étape ne qualifie pas le droit et n'appelle aucun modèle : elle rend seulement
le texte primaire lisible au moteur lorsqu'un titre seul est insuffisant.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from scripts.collect_dila_jorf import evidence_from_archive, fetch
    from scripts.prepare_motor_input import prepare
except ModuleNotFoundError:  # pragma: no cover - direct workflow invocation.
    from collect_dila_jorf import evidence_from_archive, fetch
    from prepare_motor_input import prepare


SCHEMA = "lawradar-jorf-candidate-excerpts-v1"
MAX_EXCERPT_CHARS = 12000


def prior_documents(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError("Index d'extraits JORF existant invalide.")
    return {
        item["text_id"]: item
        for item in payload.get("documents", [])
        if isinstance(item, dict) and isinstance(item.get("text_id"), str)
    }


def archive_lookup(summary: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for edition in summary.get("editions", []):
        url = edition.get("archive_url")
        if not isinstance(url, str) or not url:
            continue
        for document in edition.get("documents", []):
            text_id = document.get("text_id")
            if isinstance(text_id, str):
                lookup[text_id] = url
    return lookup


def excerpt_entry(document: dict[str, Any]) -> dict[str, Any]:
    plain_text = "\n".join(
        article.get("plain_text", "")
        for article in document.get("articles", [])
        if isinstance(article, dict) and isinstance(article.get("plain_text"), str)
    ).strip()
    excerpt = plain_text[:MAX_EXCERPT_CHARS]
    return {
        "text_id": document["text_id"],
        "archive_url": document["archive_url"],
        "archive_sha256": document["archive_sha256"],
        "content_status": "AVAILABLE" if excerpt else "UNAVAILABLE",
        "official_text_excerpt": excerpt or None,
        "official_text_sha256": hashlib.sha256(plain_text.encode("utf-8")).hexdigest() if plain_text else None,
        "excerpt_truncated": len(plain_text) > len(excerpt),
    }


def enrich(evidence_dir: Path, existing: Path) -> dict[str, Any]:
    """Fetches each relevant DILA archive once and extracts only current candidates."""
    prepared = prepare(evidence_dir)
    wanted = {
        record["evidence"]["text_id"]
        for record in prepared.get("candidates", [])
        if record.get("source_kind") == "JORF"
        and isinstance(record.get("evidence", {}).get("text_id"), str)
    }
    retained = prior_documents(existing)
    summary = json.loads((evidence_dir / "jorf-summaries-latest.json").read_text(encoding="utf-8"))
    locations = archive_lookup(summary)
    errors: list[dict[str, str]] = []
    grouped: dict[str, set[str]] = {}
    for text_id in sorted(wanted):
        archive_url = locations.get(text_id)
        if archive_url is None:
            errors.append({"text_id": text_id, "reason": "ARCHIVE_LOCATION_MISSING"})
            continue
        grouped.setdefault(archive_url, set()).add(text_id)

    with tempfile.TemporaryDirectory(prefix="lawradar-jorf-excerpts-") as temporary:
        root = Path(temporary)
        for position, (archive_url, text_ids) in enumerate(grouped.items()):
            archive = root / f"archive-{position}.tar.gz"
            output = root / f"extract-{position}"
            try:
                fetch(archive_url, archive)
                evidence_from_archive(archive, archive_url, text_ids, output)
                for text_id in text_ids:
                    path = output / "documents" / f"{text_id}.json"
                    if path.exists():
                        retained[text_id] = excerpt_entry(json.loads(path.read_text(encoding="utf-8")))
                    else:
                        errors.append({"text_id": text_id, "reason": "TEXT_NOT_FOUND_IN_ARCHIVE"})
            except Exception as exc:  # The primary collector stays available if one archive is temporarily unavailable.
                for text_id in text_ids:
                    errors.append({"text_id": text_id, "reason": f"ARCHIVE_FETCH_FAILED:{type(exc).__name__}"})

    return {
        "schema": SCHEMA,
        "status": "COMPLETED" if not errors else "PARTIAL",
        "documents": [retained[text_id] for text_id in sorted(retained)],
        "errors": errors,
        "interpretation": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=Path("evidence"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = enrich(args.evidence, args.output)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "documents": len(payload["documents"]), "errors": len(payload["errors"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
