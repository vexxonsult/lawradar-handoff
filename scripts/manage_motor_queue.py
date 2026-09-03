#!/usr/bin/env python3
"""Conserve et avance une file déterministe des candidats du moteur LawRadar."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.prepare_motor_input import prepare
except ModuleNotFoundError:  # pragma: no cover - direct workflow invocation.
    from prepare_motor_input import prepare


SCHEMA = "lawradar-motor-queue-v1"
HISTORY_LIMIT = 5000
DEFAULT_BATCH_SIZE = 250


def fingerprint(candidate: dict[str, Any]) -> str:
    raw = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def empty_queue() -> dict[str, Any]:
    return {"schema": SCHEMA, "pending": [], "processed": []}


def validate_queue(queue: dict[str, Any]) -> None:
    if queue.get("schema") != SCHEMA or not isinstance(queue.get("pending"), list) or not isinstance(queue.get("processed"), list):
        raise ValueError("File moteur invalide.")
    for item in [*queue["pending"], *queue["processed"]]:
        if not isinstance(item, dict) or not isinstance(item.get("fingerprint"), str) or not item["fingerprint"]:
            raise ValueError("Entrée de file moteur invalide.")
    for item in queue["pending"]:
        if not isinstance(item.get("candidate"), dict):
            raise ValueError("Candidat en attente invalide.")


def primary_text_unavailable(item: dict[str, Any]) -> bool:
    candidate = item["candidate"]
    evidence = candidate.get("evidence", {})
    return (
        candidate.get("source_kind") == "JORF"
        and evidence.get("content_status") == "UNAVAILABLE"
    )


def stage_prepared(prepared: dict[str, Any], queue: dict[str, Any], batch_size: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Adds unseen candidates and exposes only the first bounded batch to the model."""
    validate_queue(queue)
    if batch_size < 1:
        raise ValueError("Taille de lot invalide.")
    known = {item["fingerprint"] for item in queue["pending"]} | {item["fingerprint"] for item in queue["processed"]}
    pending = list(queue["pending"])
    for candidate in prepared.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        key = fingerprint(candidate)
        if key not in known:
            source_id = candidate.get("source_id")
            # A pending title-only record is replaced in place when the same
            # official text gains a deterministic excerpt. A processed older
            # version remains auditable, while the better-evidenced version is
            # intentionally eligible for one new interpretation.
            replacement = next((
                index for index, item in enumerate(pending)
                if item["candidate"].get("source_id") == source_id
            ), None)
            if replacement is None:
                pending.append({"fingerprint": key, "candidate": candidate})
            else:
                known.discard(pending[replacement]["fingerprint"])
                pending[replacement] = {"fingerprint": key, "candidate": candidate}
            known.add(key)
    # A DILA document with no primary text cannot be interpreted from its title.
    # Mark it explicitly UNRESOLVED without an LLM call. If the source later
    # yields a text excerpt, its changed fingerprint is eligible again.
    unavailable = [item for item in pending if primary_text_unavailable(item)]
    pending = [item for item in pending if not primary_text_unavailable(item)]
    timestamp = datetime.now(UTC).isoformat()
    processed = [*queue["processed"], *[
        {
            "fingerprint": item["fingerprint"],
            "source_id": item["candidate"].get("source_id"),
            "processed_at_utc": timestamp,
            "deterministic_status": "UNRESOLVED",
            "reason": "PRIMARY_TEXT_EMPTY",
        }
        for item in unavailable
    ]]
    staged = {"schema": SCHEMA, "pending": pending, "processed": processed[-HISTORY_LIMIT:]}
    motor_input = {key: value for key, value in prepared.items() if key != "candidates"}
    motor_input["candidates"] = [item["candidate"] for item in pending[:batch_size]]
    motor_input["deterministically_unresolved_candidates"] = [
        {"source_id": item["candidate"].get("source_id"), "reason": "PRIMARY_TEXT_EMPTY"}
        for item in unavailable
    ]
    return staged, motor_input


def advance(queue: dict[str, Any], motor_input: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Removes a successfully delivered batch and retains a compact audit history."""
    validate_queue(queue)
    selected = {fingerprint(item) for item in motor_input.get("candidates", []) if isinstance(item, dict)}
    if not selected:
        raise ValueError("Aucun candidat traité à retirer de la file.")
    timestamp = (now or datetime.now(UTC)).isoformat()
    completed = [item for item in queue["pending"] if item["fingerprint"] in selected]
    if len(completed) != len(selected):
        raise ValueError("Le lot livré ne correspond pas à la file moteur.")
    pending = [item for item in queue["pending"] if item["fingerprint"] not in selected]
    processed = [*queue["processed"], *[
        {"fingerprint": item["fingerprint"], "source_id": item["candidate"].get("source_id"), "processed_at_utc": timestamp}
        for item in completed
    ]]
    return {"schema": SCHEMA, "pending": pending, "processed": processed[-HISTORY_LIMIT:]}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty_queue()


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def effective_batch_size(configured_size: int, active_state_path: Path | None) -> int:
    """Conserve la taille d'un batch actif pendant une migration de plafond."""
    if active_state_path is None or not active_state_path.exists():
        return configured_size
    state = json.loads(active_state_path.read_text(encoding="utf-8"))
    if state.get("processing_status") == "ended":
        return configured_size
    request_count = state.get("request_count")
    if not isinstance(request_count, int) or request_count < 1:
        raise ValueError("État de batch actif sans request_count valide.")
    return request_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--evidence", type=Path, default=Path("evidence"))
    stage.add_argument("--queue", type=Path, required=True)
    stage.add_argument("--queue-output", type=Path, required=True)
    stage.add_argument("--batch-output", type=Path, required=True)
    stage.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    stage.add_argument("--active-batch-state", type=Path)
    complete = commands.add_parser("advance")
    complete.add_argument("--queue", type=Path, required=True)
    complete.add_argument("--motor-input", type=Path, required=True)
    complete.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "stage":
        batch_size = effective_batch_size(args.batch_size, args.active_batch_state)
        queue, motor_input = stage_prepared(prepare(args.evidence), load(args.queue), batch_size)
        write(args.queue_output, queue)
        write(args.batch_output, motor_input)
    else:
        write(args.output, advance(load(args.queue), json.loads(args.motor_input.read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
