#!/usr/bin/env python3
"""Build a bounded, evidence-backed queue for retained ``INVESTIGATE`` signals.

The queue is not a second decision engine.  It makes the unresolved evidence
visible, distinguishes a retryable technical fault from a business question,
and prevents an otherwise open signal from being silently retried forever.
It reads the immutable client context and writes a separate operational record.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


SCHEMA = "lawradar-investigation-queue-v1"
MAX_AUTOMATIC_ATTEMPTS = 2
RETRY_DELAY = timedelta(hours=6)
# Bump this only when a deterministic qualification-contract repair makes a
# previously counted technical retry non-comparable. It grants one clean retry,
# not an unlimited loop.
QUALIFICATION_CONTRACT_VERSION = "tool-envelope-v2"


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def _previous_by_signal(previous: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(previous, dict) or previous.get("schema") != SCHEMA:
        return {}
    return {
        item["signal_id"]: item
        for item in previous.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("signal_id"), str)
    }


def _result(signal: dict[str, Any], agent: str) -> dict[str, Any] | None:
    slot = signal.get("enrichments", {}).get(agent)
    if not isinstance(slot, dict):
        return None
    result = slot.get("result")
    return result if isinstance(result, dict) else None


def _has_rate_limit(result: dict[str, Any]) -> bool:
    return any("429" in str(item) or "rate-limit" in str(item).lower() for item in result.get("limitations", []))


def _question(question_id: str, kind: str, prompt: str, evidence: list[str], *, automatic: bool) -> dict[str, Any]:
    return {
        "id": question_id,
        "kind": kind,
        "status": "OPEN",
        "question": prompt,
        "evidence": evidence,
        "automatic_retry": automatic,
    }


def _questions(signal: dict[str, Any]) -> list[dict[str, Any]]:
    filters = signal.get("deterministic_filters")
    filters = filters if isinstance(filters, dict) else {}
    facts = signal.get("opportunity_facts") or signal.get("facts")
    facts = facts if isinstance(facts, dict) else {}
    requirements = facts.get("requirements") if isinstance(facts.get("requirements"), dict) else {}
    questions: list[dict[str, Any]] = []

    if filters.get("final_constraint") == "INVESTIGATE":
        missing: list[str] = []
        if requirements.get("required_authorizations"):
            missing.append("l'autorisation, l'agrément ou la voie de sous-traitance applicable")
        if requirements.get("dependencies"):
            missing.append("les dépendances opérationnelles nécessaires")
        if requirements.get("minimum_startup_capital_eur") is None:
            missing.append("le capital de démarrage nécessaire")
        if requirements.get("estimated_time_to_market_weeks") is None:
            missing.append("le délai réaliste de mise sur le marché")
        questions.append(_question(
            "OPERATIONAL_FEASIBILITY",
            "NEW_OFFICIAL_OR_PARTNER_EVIDENCE",
            "Confirmer " + (", ".join(missing) if missing else "les prérequis opérationnels")
            + " avant toute décision commerciale.",
            list((filters.get("feasibility") or {}).get("reasons", [])),
            automatic=False,
        ))

    press = _result(signal, "press")
    if press and press.get("status") == "UNRESOLVED":
        technical = _has_rate_limit(press) or "réponse claude non exploitable" in " ".join(press.get("limitations", [])).lower()
        questions.append(_question(
            "PRESS_QUALIFICATION",
            "TECHNICAL_RETRY" if technical else "EDITORIAL_LINK_REVIEW",
            "Requalifier exclusivement les candidats Presse déjà collectés ; aucune nouvelle conclusion médiatique n'est admise sans URL tracée.",
            list(press.get("limitations", [])),
            automatic=technical,
        ))

    market = _result(signal, "market")
    if market and market.get("status") == "UNRESOLVED":
        technical = "réponse claude non exploitable" in " ".join(market.get("limitations", [])).lower()
        questions.append(_question(
            "MARKET_RELEVANCE",
            "TECHNICAL_RETRY" if technical else "DIRECT_PROCUREMENT_LINK_REVIEW",
            "Déterminer si un avis BOAMP cite le texte, son obligation ou un besoin directement lié ; un simple mot-sectoriel ne démontre pas une demande causée par le texte.",
            list(market.get("limitations", [])),
            automatic=technical,
        ))
    return questions


def build(context: dict[str, Any], readiness: dict[str, Any], previous: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    if context.get("schema") != "lawradar-universal-signal-v2":
        raise ValueError("La file d'enquête attend un contexte universel V2.")
    if readiness.get("schema") != "lawradar-agent-pilot-readiness-v1":
        raise ValueError("La file d'enquête attend le manifeste de préparation valide.")
    current = now or datetime.now(UTC)
    ready_by_id = {
        item.get("signal_id"): item
        for item in readiness.get("signals", [])
        if isinstance(item, dict) and isinstance(item.get("signal_id"), str)
    }
    old = _previous_by_signal(previous)
    items: list[dict[str, Any]] = []

    for signal in context.get("signals", []):
        if not isinstance(signal, dict) or signal.get("radar", {}).get("status") != "RETAINED":
            continue
        signal_id = signal.get("id")
        if not isinstance(signal_id, str):
            continue
        readiness_item = ready_by_id.get(signal_id, {})
        questions = _questions(signal)
        if not questions:
            continue
        old_item = old.get(signal_id, {})
        automatic = any(item["automatic_retry"] for item in questions)
        same_contract = old_item.get("qualification_contract_version") == QUALIFICATION_CONTRACT_VERSION
        previous_attempts = (
            int(old_item.get("automatic_attempts", 0))
            if same_contract and isinstance(old_item.get("automatic_attempts", 0), int)
            else 0
        )
        attempts = previous_attempts + 1 if automatic else previous_attempts
        exhausted = automatic and attempts >= MAX_AUTOMATIC_ATTEMPTS
        state = "REVIEW_REQUIRED" if exhausted else "WAITING_FOR_EVIDENCE"
        next_retry = (current + RETRY_DELAY).isoformat() if automatic and not exhausted else None
        title = signal.get("opportunity_facts", {}).get("title") or signal.get("facts", {}).get("title") or signal.get("source", {}).get("evidence", {}).get("official", {}).get("title")
        items.append({
            "signal_id": signal_id,
            "source_id": signal.get("source", {}).get("source_id"),
            "title": title if isinstance(title, str) else None,
            "status": state,
            "opened_at_utc": old_item.get("opened_at_utc") if isinstance(old_item.get("opened_at_utc"), str) else current.isoformat(),
            "updated_at_utc": current.isoformat(),
            "automatic_attempts": attempts,
            "max_automatic_attempts": MAX_AUTOMATIC_ATTEMPTS,
            "qualification_contract_version": QUALIFICATION_CONTRACT_VERSION,
            "next_retry_not_before_utc": next_retry,
            "questions": questions,
            "readiness_status": readiness_item.get("status"),
            "final_constraint": (readiness_item.get("filters") or {}).get("final_constraint"),
        })
    return {
        "schema": SCHEMA,
        "generated_at_utc": current.isoformat(),
        "source_run": context.get("run", {}),
        "policy": {"max_automatic_attempts": MAX_AUTOMATIC_ATTEMPTS, "retry_delay_hours": int(RETRY_DELAY.total_seconds() // 3600)},
        "items": items,
        "summary": {
            "open_count": sum(item["status"] == "WAITING_FOR_EVIDENCE" for item in items),
            "review_required_count": sum(item["status"] == "REVIEW_REQUIRED" for item in items),
            "automatic_retry_count": sum(any(question["automatic_retry"] for question in item["questions"]) and item["status"] == "WAITING_FOR_EVIDENCE" for item in items),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    previous = json.loads(args.previous.read_text(encoding="utf-8")) if args.previous and args.previous.exists() else None
    result = build(
        json.loads(args.context.read_text(encoding="utf-8")),
        json.loads(args.readiness.read_text(encoding="utf-8")),
        previous,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
