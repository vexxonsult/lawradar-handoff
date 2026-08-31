#!/usr/bin/env python3
"""Construit l'entrée compacte et diffée du moteur LawRadar."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def git_version(path: Path, revision: str) -> dict[str, Any] | None:
    try:
        raw = subprocess.check_output(
            ["git", "show", f"{revision}:{path.as_posix()}"], text=True
        )
    except subprocess.CalledProcessError:
        return None
    return json.loads(raw)


def last_two_revisions(path: Path) -> list[str]:
    raw = subprocess.check_output(
        ["git", "log", "-2", "--format=%H", "--", path.as_posix()], text=True
    )
    return [line for line in raw.splitlines() if line]


def changed_records(
    current: dict[str, Any], previous: dict[str, Any] | None, kind: str
) -> list[dict[str, Any]]:
    if kind == "JORF":
        current_map = {
            doc["text_id"]: doc
            for edition in current.get("editions", [])
            for doc in edition.get("documents", [])
        }
        previous_map = {
            doc["text_id"]: doc
            for edition in (previous or {}).get("editions", [])
            for doc in edition.get("documents", [])
        }
        prefix, key = "jorf", "text_id"
    else:
        current_map = {doc["url"]: doc for doc in current.get("documents", [])}
        previous_map = {doc["url"]: doc for doc in (previous or {}).get("documents", [])}
        prefix, key = "consultdd", "url"
    records = []
    for identifier, document in current_map.items():
        prior = previous_map.get(identifier)
        if prior == document:
            continue
        records.append({
            "source_id": f"{prefix}:{identifier}",
            "source_kind": kind,
            "change": "NEW" if prior is None else "CHANGED",
            "evidence": document,
        })
    return records


def prepare(evidence_dir: Path) -> dict[str, Any]:
    delta = json.loads((evidence_dir / "delta-latest.json").read_text(encoding="utf-8"))
    jorf_current = json.loads(
        (evidence_dir / "jorf-summaries-latest.json").read_text(encoding="utf-8")
    )
    candidates: list[dict[str, Any]] = []
    source_specs = (
        ("jorf-summaries-latest.json", "JORF"),
        ("consultdd-latest.json", "CONSULTDD"),
    )
    for filename, kind in source_specs:
        if filename not in delta.get("changed_sources", []):
            continue
        path = evidence_dir / filename
        revisions = last_two_revisions(path)
        current = json.loads(path.read_text(encoding="utf-8"))
        previous = git_version(path, revisions[1]) if len(revisions) > 1 else None
        candidates.extend(changed_records(current, previous, kind))
    return {
        "schema": "lawradar-motor-input-v1",
        "report_date": jorf_current.get("coverage_end") or "indéterminée",
        "delta_changed_sources": delta.get("changed_sources", []),
        "candidates": candidates,
        "rules": "Preuves locales diffées uniquement ; aucun accès réseau ; inconnu = UNRESOLVED.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=Path("evidence"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(prepare(args.evidence), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
