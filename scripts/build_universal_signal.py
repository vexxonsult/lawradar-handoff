#!/usr/bin/env python3
"""Construit le dossier universel de signal sans nouvelle interprétation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def signal_id(report_date: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{report_date}|{source_id}".encode("utf-8")).hexdigest()[:16]
    return f"signal:{digest}"


def compact_evidence(evidence: Any) -> dict[str, Any] | None:
    """Conserve des références vérifiables sans recopier la preuve primaire."""
    if not isinstance(evidence, dict):
        return None
    detail = evidence.get("official_detail")
    detail = detail if isinstance(detail, dict) else {}
    attachments = evidence.get("official_attachments")
    attachments = attachments if isinstance(attachments, list) else []
    excerpts = evidence.get("financial_evidence")
    excerpts = excerpts if isinstance(excerpts, list) else []

    one_excerpt_per_page: list[dict[str, Any]] = []
    seen_pages: set[tuple[Any, Any]] = set()
    for item in excerpts:
        if not isinstance(item, dict):
            continue
        key = (item.get("source_url"), item.get("page"))
        if key in seen_pages:
            continue
        seen_pages.add(key)
        excerpt = item.get("excerpt")
        one_excerpt_per_page.append({
            "source_url": item.get("source_url"),
            "page": item.get("page"),
            "excerpt": excerpt[:500] if isinstance(excerpt, str) else excerpt,
        })
        if len(one_excerpt_per_page) == 8:
            break

    return {
        "title": evidence.get("title"),
        "url": evidence.get("url"),
        "dates": evidence.get("dates", []),
        "detail_status": evidence.get("detail_status"),
        "official": {
            "title": detail.get("official_title"),
            "period": detail.get("official_period"),
        },
        "attachments": [
            {"url": item.get("url"), "label": item.get("label")}
            for item in attachments if isinstance(item, dict)
        ],
        "evidence_excerpts": one_excerpt_per_page,
    }


def build_dossier(
    motor_input: dict[str, Any], delivery: dict[str, Any], run_manifest: dict[str, Any]
) -> dict[str, Any]:
    if motor_input.get("schema") != "lawradar-motor-input-v1":
        raise ValueError("Entrée moteur non prise en charge.")
    if delivery.get("schema") != "lawradar-motor-delivery-v1":
        raise ValueError("Livraison moteur non prise en charge.")
    if run_manifest.get("schema") != "lawradar-run-manifest-v1":
        raise ValueError("Manifeste de run non pris en charge.")
    report_date = motor_input.get("report_date")
    if not isinstance(report_date, str) or not report_date:
        raise ValueError("Date de rapport invalide.")
    candidates = motor_input.get("candidates")
    opportunities = delivery.get("opportunities")
    if not isinstance(candidates, list) or not isinstance(opportunities, list):
        raise ValueError("Candidats ou opportunités invalides.")
    candidate_by_source = {
        item.get("source_id"): item
        for item in candidates
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    if len(candidate_by_source) != len(candidates):
        raise ValueError("Chaque candidat doit porter un source_id unique.")
    opportunity_by_source = {
        item.get("source_id"): item
        for item in opportunities
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    if len(opportunity_by_source) != len(opportunities) or set(opportunity_by_source) != set(candidate_by_source):
        raise ValueError("Chaque candidat doit recevoir exactement une décision moteur.")
    signals = []
    for source_id in sorted(candidate_by_source):
        candidate = candidate_by_source[source_id]
        decision = opportunity_by_source[source_id]
        signals.append({
            "id": signal_id(report_date, source_id),
            "source": {
                "source_id": source_id,
                "source_kind": candidate.get("source_kind"),
                "change": candidate.get("change"),
                "evidence": compact_evidence(candidate.get("evidence")),
            },
            "radar": {
                "status": decision.get("status"),
                "reason": decision.get("reason"),
            },
            "enrichments": {
                "press": {"status": "PENDING", "result": None},
                "demand": {"status": "PENDING", "result": None},
                "market": {"status": "PENDING", "result": None},
            },
        })
    run = run_manifest.get("run", {})
    unresolved = sum(item["radar"]["status"] == "UNRESOLVED" for item in signals)
    return {
        "schema": "lawradar-universal-signal-v1",
        "run": {
            "id": run.get("id"),
            "url": run.get("url"),
            "commit": run.get("commit"),
            "report_date": report_date,
        },
        "context": {
            "coverage": delivery.get("run", {}).get("coverage"),
            "delta_changed_sources": motor_input.get("delta_changed_sources", []),
            "handled_source_files": motor_input.get("handled_source_files", []),
            "rule": motor_input.get("rules"),
        },
        "signals": signals,
        "money_flows": delivery.get("money_flows", []),
        "quality": {
            "opportunity_count": len(signals),
            "unresolved_count": unresolved,
            "money_flow_count": len(delivery.get("money_flows", [])),
            "limitation": "Les enrichissements sont vides tant qu'aucun agent dédié n'a produit une sortie sourcée.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--motor-input", type=Path, required=True)
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dossier = build_dossier(
        json.loads(args.motor_input.read_text(encoding="utf-8")),
        json.loads(args.delivery.read_text(encoding="utf-8")),
        json.loads(args.run_manifest.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dossier, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
