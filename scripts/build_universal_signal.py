#!/usr/bin/env python3
"""Construit le dossier universel de signal sans nouvelle interprétation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any


MAX_PRIMARY_EXCERPT_CHARS = 2000
READING_FIELDS = (
    "consequence", "affected_actors", "beneficiaries", "constrained_parties",
    "potential_service_partners", "unknowns",
)
LEGACY_FLOW_ID = re.compile(r"^MF-(\d+)-\d+$")


def signal_id(report_date: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{report_date}|{source_id}".encode("utf-8")).hexdigest()[:16]
    return f"signal:{digest}"


def stable_source_id(source_id: str) -> str:
    """Identity shared by every future observation of one official source."""
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]
    return f"source:{digest}"


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compact_excerpt(value: Any, limit: int = MAX_PRIMARY_EXCERPT_CHARS) -> str | None:
    """Keep a readable head and operative tail without cloning the source."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if len(text) <= limit:
        return text
    marker = "\n[… extrait primaire compacté …]\n"
    available = limit - len(marker)
    head = (available * 3) // 4
    return f"{text[:head]}{marker}{text[-(available - head):]}"


def compact_evidence(evidence: Any) -> dict[str, Any] | None:
    """Conserve les références et un aperçu sans recopier la preuve intégrale."""
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

    text_id = evidence.get("text_id")
    official_url = evidence.get("official_url") or evidence.get("url")
    if not official_url and isinstance(text_id, str) and text_id.startswith("JORFTEXT"):
        official_url = f"https://www.legifrance.gouv.fr/jorf/id/{text_id}"
    excerpt = compact_excerpt(evidence.get("official_text_excerpt"))
    excerpt_was_compacted = (
        isinstance(evidence.get("official_text_excerpt"), str)
        and excerpt is not None
        and len(evidence["official_text_excerpt"].strip()) > len(excerpt)
    )

    return {
        "text_id": text_id,
        "nature": evidence.get("nature"),
        "nor": evidence.get("nor"),
        "title": evidence.get("title"),
        "publisher": evidence.get("source_publisher") or (
            "DILA / Journal officiel de la République française"
            if isinstance(text_id, str) and text_id.startswith("JORFTEXT")
            else None
        ),
        "url": official_url or evidence.get("archive_url"),
        "publication_date": evidence.get("publication_date"),
        "journal_number": evidence.get("journal_number"),
        "article_ids": evidence.get("article_ids", []),
        "article_titles": evidence.get("article_titles", []),
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
        "primary_evidence": {
            "content_status": evidence.get("content_status"),
            "text_sha256": evidence.get("official_text_sha256"),
            "excerpt": excerpt,
            "excerpt_truncated": bool(evidence.get("excerpt_truncated")) or excerpt_was_compacted,
            "archive_url": evidence.get("archive_url"),
            "archive_sha256": evidence.get("archive_sha256"),
        },
    }


def preserved_reading(
    decision: dict[str, Any], source_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Expose the paid factual reading to every downstream client.

    Historical deliveries may predate this field. They remain explicitly
    missing: no compatibility layer is allowed to masquerade as paid analysis.
    """
    value = decision.get("reading")
    available = (
        isinstance(value, dict)
        and set(value) == set(READING_FIELDS)
        and isinstance(value.get("consequence"), str)
        and bool(value["consequence"].strip())
        and all(isinstance(value.get(field), list) for field in READING_FIELDS[1:])
    )
    historical_fallback = available and any(
        isinstance(item, str) and item.startswith("Batch lancé avant la lecture structurée")
        for item in value.get("unknowns", [])
    )
    if available and not historical_fallback:
        reading = copy.deepcopy(value)
        status = "AVAILABLE"
        basis = "CANDIDATE_EVIDENCE_ONLY"
        # The universal contract records the component that transported and
        # validated the structured reading, not an unverifiable vendor/model
        # claim.  Provider details belong to the immutable run metadata.
        producer = "MOTOR_STRUCTURED_READING"
    else:
        reading = None
        status = "MISSING_LEGACY"
        basis = None
        producer = "LEGACY_COMPATIBILITY"
    provenance = {
        "status": status,
        "basis": basis,
        "producer": producer,
        "source_id": source_id,
    }
    return reading, provenance


def bind_money_flows(
    flows: Any,
    source_order: list[str],
    signal_id_by_source: dict[str, str],
) -> list[dict[str, Any]]:
    """Attach every global flow to its official source and daily signal.

    New deliveries carry ``source_id`` directly. Older aggregate deliveries
    encoded the candidate position in ``MF-01-01``; that relation is recovered
    deterministically. Anything older remains visible but explicitly unlinked.
    """
    if not isinstance(flows, list):
        raise ValueError("Flux financiers invalides dans la livraison moteur.")
    bound: list[dict[str, Any]] = []
    for flow in flows:
        if not isinstance(flow, dict):
            raise ValueError("Flux financier non structuré dans la livraison moteur.")
        item = copy.deepcopy(flow)
        source_id = item.get("source_id")
        if source_id is None:
            match = LEGACY_FLOW_ID.fullmatch(str(item.get("id") or ""))
            position = int(match.group(1)) - 1 if match else -1
            if 0 <= position < len(source_order):
                source_id = source_order[position]
        if source_id is not None and source_id not in signal_id_by_source:
            raise ValueError("Flux financier rattaché à une source absente du lot.")
        item["source_id"] = source_id
        item["signal_id"] = signal_id_by_source.get(source_id) if source_id else None
        item["link_status"] = "VERIFIED" if source_id else "UNRESOLVED_LEGACY"
        bound.append(item)
    return bound


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
    signal_id_by_source: dict[str, str] = {}
    for source_id in sorted(candidate_by_source):
        candidate = candidate_by_source[source_id]
        decision = opportunity_by_source[source_id]
        facts = decision.get("facts")
        if not isinstance(facts, dict) or facts.get("schema") != "lawradar-opportunity-facts-v1":
            raise ValueError("Faits d'opportunité absents de la livraison moteur.")
        if facts.get("signal_id") != source_id:
            raise ValueError("Faits d'opportunité rattachés au mauvais candidat.")
        current_signal_id = signal_id(report_date, source_id)
        signal_id_by_source[source_id] = current_signal_id
        bound_facts = copy.deepcopy(facts)
        # The model identifies only the immutable source candidate. This binder
        # assigns the deterministic universal-signal id used by later agents.
        bound_facts["signal_id"] = current_signal_id
        compacted_evidence = compact_evidence(candidate.get("evidence"))
        reading, reading_provenance = preserved_reading(decision, source_id)
        signals.append({
            "id": current_signal_id,
            "identity": {
                "stable_source_id": stable_source_id(source_id),
                "evidence_version": f"sha256:{canonical_hash(candidate.get('evidence'))}",
            },
            "source": {
                "source_id": source_id,
                "source_kind": candidate.get("source_kind"),
                "change": candidate.get("change"),
                "evidence": compacted_evidence,
            },
            "radar": {
                "status": decision.get("status"),
                "reason": decision.get("reason"),
            },
            "discovery": copy.deepcopy(candidate.get("discovery")),
            "reading": reading,
            "reading_provenance": reading_provenance,
            "opportunity_facts": bound_facts,
            "enrichments": {
                "press": {"status": "PENDING", "result": None},
                "demand": {"status": "PENDING", "result": None},
                "market": {"status": "PENDING", "result": None},
            },
        })
    run = run_manifest.get("run", {})
    source_order = [item["source_id"] for item in candidates]
    money_flows = bind_money_flows(
        delivery.get("money_flows", []), source_order, signal_id_by_source
    )
    unresolved = sum(item["radar"]["status"] == "UNRESOLVED" for item in signals)
    readings_available = sum(
        item["reading_provenance"]["status"] == "AVAILABLE" for item in signals
    )
    evidence_references = sum(
        bool((item.get("source", {}).get("evidence") or {}).get("url"))
        for item in signals
    )
    return {
        "schema": "lawradar-universal-signal-v2",
        "run": {
            "id": run.get("id"),
            "attempt": run.get("attempt"),
            "url": run.get("url"),
            "commit": run.get("commit"),
            "report_date": report_date,
        },
        "context": {
            "coverage": delivery.get("run", {}).get("coverage"),
            "delta_changed_sources": motor_input.get("delta_changed_sources", []),
            "handled_source_files": motor_input.get("handled_source_files", []),
            "rule": motor_input.get("rules"),
            # These deterministic exits never reach Claude, yet they are the
            # most important population when auditing false negatives. Keep
            # their compact routing trace in every immutable run archive.
            "prefilter_audit": {
                "excluded_historical_candidates": copy.deepcopy(
                    motor_input.get("excluded_historical_candidates", [])
                ),
                "excluded_routine_candidates": copy.deepcopy(
                    motor_input.get("excluded_routine_candidates", [])
                ),
                "excluded_no_economic_friction_candidates": copy.deepcopy(
                    motor_input.get("excluded_no_economic_friction_candidates", [])
                ),
                "deterministically_unresolved_candidates": copy.deepcopy(
                    motor_input.get("deterministically_unresolved_candidates", [])
                ),
            },
        },
        "signals": signals,
        "money_flows": money_flows,
        "quality": {
            "opportunity_count": len(signals),
            "unresolved_count": unresolved,
            "readings_available_count": readings_available,
            "evidence_reference_count": evidence_references,
            "money_flow_count": len(money_flows),
            "money_flow_unlinked_count": sum(
                item["link_status"] != "VERIFIED" for item in money_flows
            ),
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
