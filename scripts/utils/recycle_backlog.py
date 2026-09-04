#!/usr/bin/env python3
"""Archive et réévalue, sans IA, les signaux LawRadar temporairement bloqués.

La file moteur contient uniquement des empreintes et des candidats avant leur
interprétation : elle ne suffit donc pas à réévaluer une opportunité. Ce module
conserve à part les faits versionnés et les décisions de filtre non ouvertes,
puis les rejoue contre la politique et le profil opérateur actuels.

Il ne modifie jamais ``evidence/universal-signal-latest.json`` et ne transforme
jamais arbitrairement un signal en PASS. Seul ``evaluate`` peut rouvrir un
enregistrement, à partir de ses faits source et des règles actuelles.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.run_deterministic_filters import evaluate
except ModuleNotFoundError:  # pragma: no cover - direct script invocation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from run_deterministic_filters import evaluate


BACKLOG_SCHEMA = "lawradar-recycle-backlog-v1"
READY_SCHEMA = "lawradar-recycle-ready-v1"
CORE_SCHEMA = "lawradar-universal-signal-v2"
MAX_ATTEMPTS = 12


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def empty_backlog() -> dict[str, Any]:
    return {"schema": BACKLOG_SCHEMA, "records": [], "queue_audit": {"unrecoverable_queue_entries": []}}


def load_json(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(fallback) if fallback is not None else {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON objet attendu : {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_backlog(backlog: dict[str, Any]) -> None:
    if backlog.get("schema") != BACKLOG_SCHEMA or not isinstance(backlog.get("records"), list):
        raise ValueError("Backlog de recyclage invalide.")
    for record in backlog["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("signal_id"), str) or not isinstance(record.get("facts"), dict):
            raise ValueError("Enregistrement de recyclage invalide.")


def reopening_status(filters: dict[str, Any]) -> str:
    access = filters.get("operator_access") if isinstance(filters.get("operator_access"), dict) else {}
    if access.get("status") == "HOLD":
        return "HOLD"
    return str(filters.get("final_constraint", "INVESTIGATE"))


def eligible(filters: dict[str, Any]) -> bool:
    access = filters.get("operator_access") if isinstance(filters.get("operator_access"), dict) else {}
    return filters.get("final_constraint") == "PASS" and access.get("allow_external_collection") is True


def compact_signal(signal: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
    """Keep source/facts/support state sufficient for a later, traceable reopen."""
    return {
        "id": signal.get("id"),
        "identity": copy.deepcopy(signal.get("identity")),
        "source": copy.deepcopy(signal.get("source")),
        "radar": copy.deepcopy(signal.get("radar")),
        "discovery": copy.deepcopy(signal.get("discovery")),
        "reading": copy.deepcopy(signal.get("reading")),
        "reading_provenance": copy.deepcopy(signal.get("reading_provenance")),
        "opportunity_facts": copy.deepcopy(signal.get("opportunity_facts")),
        "enrichments": copy.deepcopy(signal.get("enrichments")),
        "deterministic_filters": copy.deepcopy(filters),
    }


def queue_audit(queue: dict[str, Any]) -> dict[str, Any]:
    """Expose queue-only records that cannot be replayed because facts are absent."""
    processed = queue.get("processed") if isinstance(queue.get("processed"), list) else []
    unresolved = [
        {"fingerprint": item.get("fingerprint"), "source_id": item.get("source_id"), "reason": item.get("reason")}
        for item in processed
        if isinstance(item, dict) and item.get("deterministic_status") == "UNRESOLVED"
    ]
    return {
        "processed_count": len(processed),
        "unrecoverable_queue_entries": unresolved,
        "note": "La file ne contient pas les faits d'opportunité : ces entrées exigent une nouvelle preuve primaire avant recyclage.",
    }


def capture(
    dossier: dict[str, Any],
    backlog: dict[str, Any],
    policy: dict[str, Any],
    profile: dict[str, Any],
    *,
    queue: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append newly blocked, fact-backed signals to the durable recycle backlog."""
    if dossier.get("schema") != CORE_SCHEMA or not isinstance(dossier.get("signals"), list):
        raise ValueError("Le recyclage attend un lawradar-universal-signal-v2.")
    validate_backlog(backlog)
    current = now or datetime.now(UTC)
    policy_hash, profile_hash = stable_hash(policy), stable_hash(profile)
    indexed = {record["signal_id"]: copy.deepcopy(record) for record in backlog["records"]}

    for signal in dossier["signals"]:
        if not isinstance(signal, dict) or signal.get("radar", {}).get("status") != "RETAINED":
            continue
        facts = signal.get("opportunity_facts")
        if not isinstance(facts, dict):
            continue
        filters = evaluate(facts, policy, profile, now=current)
        status = reopening_status(filters)
        signal_id = signal.get("id")
        if not isinstance(signal_id, str) or not signal_id:
            continue
        # A signal already PASS belongs to the normal path, not to this backlog.
        if status == "PASS" and eligible(filters):
            continue
        existing = indexed.get(signal_id)
        facts_hash = stable_hash(facts)
        attempt = {
            "at_utc": current.isoformat(),
            "trigger": "CAPTURE",
            "status": status,
            "policy_sha256": policy_hash,
            "profile_sha256": profile_hash,
        }
        if existing and existing.get("facts_sha256") == facts_hash:
            attempts = existing.get("attempts", [])
            previous = attempts[-1] if attempts else {}
            existing["latest_filters"] = filters
            existing["latest_status"] = status
            existing["state"] = "BACKLOG"
            existing["signal"] = compact_signal(signal, filters)
            # Avoid a daily history churn when neither facts nor rules changed.
            if previous.get("policy_sha256") != policy_hash or previous.get("profile_sha256") != profile_hash or previous.get("status") != status:
                existing["attempts"] = [*attempts, attempt][-MAX_ATTEMPTS:]
            indexed[signal_id] = existing
            continue
        indexed[signal_id] = {
            "signal_id": signal_id,
            "source_id": signal.get("source", {}).get("source_id") if isinstance(signal.get("source"), dict) else None,
            "captured_at_utc": current.isoformat(),
            "facts_sha256": facts_hash,
            "initial_status": status,
            "latest_status": status,
            "state": "BACKLOG",
            "initial_filters": filters,
            "latest_filters": filters,
            "signal": compact_signal(signal, filters),
            "facts": copy.deepcopy(facts),
            "attempts": [attempt],
        }

    return {
        "schema": BACKLOG_SCHEMA,
        "records": [indexed[key] for key in sorted(indexed)],
        "queue_audit": queue_audit(queue or {}),
    }


def recycle(backlog: dict[str, Any], policy: dict[str, Any], profile: dict[str, Any], *, now: datetime | None = None, force: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-evaluate durable records; only a true PASS appears in the ready manifest."""
    validate_backlog(backlog)
    current = now or datetime.now(UTC)
    policy_hash, profile_hash = stable_hash(policy), stable_hash(profile)
    updated: list[dict[str, Any]] = []
    reopened: list[dict[str, Any]] = []
    for original in backlog["records"]:
        record = copy.deepcopy(original)
        last_attempt = record.get("attempts", [])[-1] if record.get("attempts") else {}
        revision_changed = last_attempt.get("policy_sha256") != policy_hash or last_attempt.get("profile_sha256") != profile_hash
        if not force and not revision_changed:
            updated.append(record)
            continue
        filters = evaluate(record["facts"], policy, profile, now=current)
        status = reopening_status(filters)
        attempt = {
            "at_utc": current.isoformat(),
            "trigger": "MANUAL_REVIEW" if force else "POLICY_OR_PROFILE_CHANGED",
            "status": status,
            "policy_sha256": policy_hash,
            "profile_sha256": profile_hash,
        }
        record["latest_filters"] = filters
        record["latest_status"] = status
        record["attempts"] = [*record.get("attempts", []), attempt][-MAX_ATTEMPTS:]
        if eligible(filters):
            record["state"] = "REOPENED"
            reopened_signal = copy.deepcopy(record["signal"])
            reopened_signal["deterministic_filters"] = filters
            reopened.append({
                "signal_id": record["signal_id"],
                "source_id": record.get("source_id"),
                "reopened_reason": attempt["trigger"],
                "signal": reopened_signal,
            })
        else:
            record["state"] = "BACKLOG"
        updated.append(record)
    next_backlog = {"schema": BACKLOG_SCHEMA, "records": updated, "queue_audit": backlog.get("queue_audit", {})}
    ready = {
        "schema": READY_SCHEMA,
        "generated_at_utc": current.isoformat(),
        "reopened_count": len(reopened),
        "reopened": reopened,
        "rule": "Un signal est rouvert seulement après réévaluation déterministe PASS et porte opérateur autorisée.",
        "next_step": "Ces signaux doivent repasser les enrichissements Presse, Demande et Marché avant tout appel du client Entrepreneur.",
    }
    return next_backlog, ready


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture", help="archive les signaux actuellement bloqués")
    capture_parser.add_argument("--dossier", type=Path, required=True)
    capture_parser.add_argument("--policy", type=Path, required=True)
    capture_parser.add_argument("--profile", type=Path, required=True)
    capture_parser.add_argument("--queue", type=Path, required=True)
    capture_parser.add_argument("--backlog", type=Path, required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    recycle_parser = commands.add_parser("recycle", help="réévalue le backlog avec le profil actuel")
    recycle_parser.add_argument("--backlog", type=Path, required=True)
    recycle_parser.add_argument("--policy", type=Path, required=True)
    recycle_parser.add_argument("--profile", type=Path, required=True)
    recycle_parser.add_argument("--output", type=Path, required=True)
    recycle_parser.add_argument("--ready-output", type=Path, required=True)
    recycle_parser.add_argument("--force", action="store_true", help="réévalue même si profil et politique sont inchangés")
    args = parser.parse_args()
    policy = load_json(args.policy)
    profile = load_json(args.profile)
    if args.command == "capture":
        output = capture(
            load_json(args.dossier),
            load_json(args.backlog, empty_backlog()),
            policy,
            profile,
            queue=load_json(args.queue, {"processed": []}),
        )
        write_json(args.output, output)
    else:
        output, ready = recycle(load_json(args.backlog, empty_backlog()), policy, profile, force=args.force)
        write_json(args.output, output)
        write_json(args.ready_output, ready)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
