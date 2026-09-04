#!/usr/bin/env python3
"""Construit l'entrée compacte et diffée du moteur LawRadar."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from scripts.discover_opportunity_friction import screen
except ModuleNotFoundError:  # pragma: no cover - direct workflow invocation.
    from discover_opportunity_friction import screen


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


def exclude_historical_jorf_records(
    records: list[dict[str, Any]], covered_dates: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Never send a reintroduced archive text to the daily interpretation queue."""
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for record in records:
        date = record.get("evidence", {}).get("publication_date")
        if isinstance(date, str) and date in covered_dates:
            candidates.append(record)
        else:
            exclusions.append({
                "source_id": record["source_id"],
                "publication_date": date,
                "reason": "HISTORICAL_REAPPEARANCE_OUTSIDE_CURRENT_COVERAGE",
            })
    return candidates, exclusions


# These patterns deliberately cover only documents whose subject is internal
# public-administration staffing or a JORF section heading. They are not a
# judgement on a topic's importance: they make the deterministic decision that
# it cannot create a general business opportunity from the metadata collected.
ROUTINE_ADMINISTRATION_PATTERNS = (
    r"\bdélégation de signature\b",
    r"\b(ouverture d.un examen professionnel|examen professionnel|concours)\b",
    r"\b(nombre de postes offerts|avis de vacance d.un emploi|avis de vacance d.emplois)\b",
    r"\b(admission à la retraite|nomination|titularisation|cessation de fonctions|réintégration|affectation|détachement|intégration)\b",
    r"\b(composition du cabinet|composition de la commission|nomination au (comité|conseil d.administration|conseil national))\b",
    r"\b(changement[s]? de nom[s]?|demandes de changement de nom[s]?)\b",
    r"^(commissions et organes de contrôle|documents déposés|documents publiés)$",
)
ROUTINE_ADMINISTRATION_RE = re.compile("|".join(ROUTINE_ADMINISTRATION_PATTERNS), re.IGNORECASE)


def exclude_routine_administration_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Route obvious staffing/section documents without spending model tokens.

    Each decision remains in the prepared input so that the audit can distinguish
    a deterministic non-opportunity from an unprocessed document.
    """
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for record in records:
        title = record.get("evidence", {}).get("title")
        if isinstance(title, str) and ROUTINE_ADMINISTRATION_RE.search(title):
            exclusions.append({
                "source_id": record["source_id"],
                "title": title,
                "reason": "ROUTINE_PUBLIC_ADMINISTRATION_TITLE",
            })
        else:
            candidates.append(record)
    return candidates, exclusions


def load_jorf_excerpt_index(path: Path) -> dict[str, dict[str, Any]]:
    """Loads compact official-text excerpts when the collector has them."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "lawradar-jorf-candidate-excerpts-v1":
        raise ValueError("Index des extraits JORF invalide.")
    return {
        item["text_id"]: item
        for item in payload.get("documents", [])
        if isinstance(item, dict) and isinstance(item.get("text_id"), str)
    }


def attach_jorf_excerpt(
    record: dict[str, Any], excerpts: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Adds only the extracted official evidence associated with this text id."""
    text_id = record.get("evidence", {}).get("text_id")
    excerpt = excerpts.get(text_id)
    if excerpt is None:
        return record
    enriched = {**record, "evidence": {**record["evidence"]}}
    for key in ("official_text_excerpt", "official_text_sha256", "excerpt_truncated", "content_status"):
        if key in excerpt:
            enriched["evidence"][key] = excerpt[key]
    return enriched


def requires_model(prepared_input: dict[str, Any]) -> bool:
    """The model is useful only when the supported sources produced candidates."""
    return bool(prepared_input.get("candidates"))


def prepare(evidence_dir: Path) -> dict[str, Any]:
    delta = json.loads((evidence_dir / "delta-latest.json").read_text(encoding="utf-8"))
    jorf_current = json.loads(
        (evidence_dir / "jorf-summaries-latest.json").read_text(encoding="utf-8")
    )
    candidates: list[dict[str, Any]] = []
    excluded_historical_candidates: list[dict[str, Any]] = []
    excluded_routine_candidates: list[dict[str, Any]] = []
    excluded_no_friction_candidates: list[dict[str, Any]] = []
    jorf_excerpts = load_jorf_excerpt_index(
        evidence_dir / "jorf-candidate-excerpts-latest.json"
    )
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
        records = changed_records(current, previous, kind)
        if kind == "JORF":
            accepted, exclusions = exclude_historical_jorf_records(
                records, set(current.get("covered_dates", []))
            )
            accepted, routine_exclusions = exclude_routine_administration_records(accepted)
            enriched, friction_exclusions = screen(
                [attach_jorf_excerpt(record, jorf_excerpts) for record in accepted]
            )
            candidates.extend(enriched)
            excluded_historical_candidates.extend(exclusions)
            excluded_routine_candidates.extend(routine_exclusions)
            excluded_no_friction_candidates.extend(friction_exclusions)
        else:
            enriched, friction_exclusions = screen(records)
            candidates.extend(enriched)
            excluded_no_friction_candidates.extend(friction_exclusions)
    return {
        "schema": "lawradar-motor-input-v1",
        "report_date": jorf_current.get("coverage_end") or "indéterminée",
        "delta_changed_sources": delta.get("changed_sources", []),
        "handled_source_files": ["jorf-summaries-latest.json", "consultdd-latest.json"],
        "candidates": candidates,
        "excluded_historical_candidates": excluded_historical_candidates,
        "excluded_routine_candidates": excluded_routine_candidates,
        "excluded_no_economic_friction_candidates": excluded_no_friction_candidates,
        "rules": "Preuves locales diffées uniquement ; réapparition historique et routine administrative explicite = filtrées avec trace ; les autres textes primaires disponibles reçoivent une lecture factuelle. Une friction détectée ouvre seulement une enquête, jamais une opportunité confirmée ; inconnu = UNRESOLVED.",
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
