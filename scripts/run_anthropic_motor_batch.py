#!/usr/bin/env python3
"""Exécute le Moteur LawRadar avec l'API Message Batches d'Anthropic.

Chaque candidat devient une requête Messages indépendante. L'identifiant du
batch est conservé afin qu'un run ultérieur puisse reprendre le même travail
sans soumettre ni facturer une seconde fois le lot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.render_motor_delivery import validate_delivery
except ModuleNotFoundError:  # Exécution directe depuis scripts/.
    from render_motor_delivery import validate_delivery


STATE_SCHEMA = "lawradar-anthropic-motor-batch-v1"
DELIVERY_SCHEMA = "lawradar-motor-delivery-v1"
DEFAULT_MODEL = "claude-sonnet-5"
MAX_CANDIDATES = 10

SYSTEM_PROMPT = """Tu es le moteur factuel LawRadar. Analyse uniquement le
candidat JSON fourni. Aucune recherche, aucun outil, aucune connaissance
externe. Toute information non démontrée reste null, MISSING, PARTIAL,
UNKNOWN ou UNRESOLVED selon le schéma. Ne déduis jamais un capital, un délai,
une autorisation, un acteur ou un flux financier. Un flux n'est admis que si
sa direction et ses acteurs sont explicitement étayés dans la preuve. Retourne
uniquement le JSON demandé, sans markdown."""


FLOW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "label", "title", "money_sentence", "explanation", "payer",
        "recipient", "amount", "effective_date", "certainty", "next_action",
    ],
    "properties": {
        name: {"type": "string", "minLength": 1}
        for name in (
            "label", "title", "money_sentence", "explanation", "payer",
            "recipient", "amount", "effective_date", "certainty", "next_action",
        )
    },
}

FACTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "signal_id", "title", "keywords", "affected_scope", "legal", "requirements", "operator_access"],
    "properties": {
        "schema": {"type": "string", "const": "lawradar-opportunity-facts-v1"},
        "signal_id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "keywords": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"type": "string", "minLength": 1}},
        "affected_scope": {"type": "array", "maxItems": 12, "items": {"type": "string", "minLength": 1}},
        "legal": {
            "type": "object",
            "additionalProperties": False,
            "required": ["jurisdiction", "text_status", "proof_status", "effective_date", "affected_scope"],
            "properties": {
                "jurisdiction": {"type": "string", "minLength": 1},
                "text_status": {"type": "string", "enum": ["PUBLISHED", "IN_FORCE", "CONSULTATION_OPEN", "DRAFT", "REPEALED", "EXPIRED", "UNKNOWN"]},
                "proof_status": {"type": "string", "enum": ["VERIFIED", "PARTIAL", "MISSING"]},
                "effective_date": {"type": ["string", "null"]},
                "affected_scope": {"type": "array", "maxItems": 12, "items": {"type": "string", "minLength": 1}},
            },
        },
        "requirements": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "required_capabilities", "required_authorizations", "dependencies",
                "minimum_startup_capital_eur", "estimated_time_to_market_weeks", "evidence_status",
            ],
            "properties": {
                "required_capabilities": {"type": "array", "maxItems": 12, "items": {"type": "string", "minLength": 1}},
                "required_authorizations": {
                    "type": "array", "maxItems": 12,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["id", "status"],
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "status": {"type": "string", "enum": ["REQUIRED", "NOT_REQUIRED", "UNKNOWN", "UNAVAILABLE"]},
                        },
                    },
                },
                "dependencies": {
                    "type": "array", "maxItems": 12,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["id", "status"],
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "status": {"type": "string", "enum": ["AVAILABLE", "UNKNOWN", "BLOCKING"]},
                        },
                    },
                },
                "minimum_startup_capital_eur": {"type": ["number", "null"], "minimum": 0},
                "estimated_time_to_market_weeks": {"type": ["number", "null"], "minimum": 0},
                "evidence_status": {"type": "string", "enum": ["VERIFIED", "PARTIAL", "MISSING"]},
            },
        },
        "operator_access": {
            "type": "object",
            "additionalProperties": False,
            "required": ["sector", "direct_offer_status", "peripheral_role_evidence", "evidence_status", "peripheral_service_evidence"],
            "properties": {
                "sector": {"type": "string", "enum": ["MEDICINES", "FINANCIAL_SERVICES", "LEGAL_SERVICES", "OTHER_REGULATED", "NOT_CLASSIFIED"]},
                "direct_offer_status": {"type": "string", "enum": ["ACCESSIBLE", "OUT_OF_PROFILE", "UNKNOWN", "NOT_APPLICABLE"]},
                "peripheral_role_evidence": {"type": "string", "enum": ["VERIFIED", "PARTIAL", "MISSING", "NOT_APPLICABLE"]},
                "evidence_status": {"type": "string", "enum": ["VERIFIED", "PARTIAL", "MISSING"]},
                "peripheral_service_evidence": {
                    "type": "array", "maxItems": 8,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "required": [
                            "service_type", "source_kind", "source_url", "excerpt",
                            "scope_excludes_regulated_acts", "scope_exclusion_excerpt", "evidence_status",
                        ],
                        "properties": {
                            "service_type": {"type": "string", "enum": ["PRESTATIONS_DE_SERVICES", "LOGICIELS", "CONSEIL", "MISE_EN_RELATION", "LOGISTIQUE"]},
                            "source_kind": {"type": "string", "enum": ["OFFICIAL_TEXT", "BOAMP"]},
                            "source_url": {"type": "string", "minLength": 1},
                            "excerpt": {"type": "string", "minLength": 1},
                            "scope_excludes_regulated_acts": {"type": "boolean"},
                            "scope_exclusion_excerpt": {"type": ["string", "null"]},
                            "evidence_status": {"type": "string", "enum": ["VERIFIED", "PARTIAL", "MISSING"]},
                        },
                    },
                },
            },
        },
    },
}

CANDIDATE_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source_id", "status", "reason", "facts", "money_flows"],
    "properties": {
        "source_id": {"type": "string", "minLength": 1},
        "status": {"type": "string", "enum": ["RETAINED", "DISCARDED", "UNRESOLVED"]},
        "reason": {"type": "string", "minLength": 1},
        "facts": FACTS_SCHEMA,
        "money_flows": {"type": "array", "maxItems": 5, "items": FLOW_SCHEMA},
    },
}


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objet JSON attendu : {path}.")
    return value


def validate_motor_input(motor_input: dict[str, Any]) -> list[dict[str, Any]]:
    if motor_input.get("schema") != "lawradar-motor-input-v1":
        raise ValueError("Schéma d'entrée moteur invalide.")
    candidates = motor_input.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Le batch exige au moins un candidat.")
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError(f"Le batch dépasse la limite stricte de {MAX_CANDIDATES} candidats.")
    source_ids: list[str] = []
    for candidate in candidates:
        source_id = candidate.get("source_id") if isinstance(candidate, dict) else None
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("Candidat sans source_id.")
        source_ids.append(source_id)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source_id dupliqué dans le batch.")
    return candidates


def _custom_id(index: int, candidate: dict[str, Any]) -> str:
    return f"candidate-{index:02d}-{_canonical_hash(candidate)[:12]}"


def build_requests(motor_input: dict[str, Any], model: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    candidates = validate_motor_input(motor_input)
    requests: list[dict[str, Any]] = []
    source_by_custom_id: dict[str, str] = {}
    for index, candidate in enumerate(candidates, start=1):
        custom_id = _custom_id(index, candidate)
        source_by_custom_id[custom_id] = candidate["source_id"]
        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": model,
                "max_tokens": 1800,
                "system": SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
                }],
                "output_config": {"format": {"type": "json_schema", "schema": CANDIDATE_RESULT_SCHEMA}},
            },
        })
    return requests, source_by_custom_id


def _request_counts(batch: Any) -> dict[str, int]:
    counts = _field(batch, "request_counts", {})
    names = ("processing", "succeeded", "errored", "canceled", "expired")
    return {name: int(_field(counts, name, 0) or 0) for name in names}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _message_text(message: Any) -> str:
    for block in _field(message, "content", []) or []:
        if _field(block, "type") == "text" and isinstance(_field(block, "text"), str):
            return _field(block, "text")
    raise ValueError("Réponse batch sans bloc texte JSON.")


def _batch_error_detail(result: Any) -> str:
    """Rend l'erreur fournisseur lisible sans la confondre avec une livraison."""
    error = _field(result, "error", {})
    error_type = str(_field(error, "type", "unknown_error"))
    message = str(_field(error, "message", "sans détail fournisseur"))
    message = " ".join(message.split())[:240]
    return f"{error_type}: {message}"


def _single_delivery(candidate_result: dict[str, Any], report_date: str) -> dict[str, Any]:
    flows = []
    for index, flow in enumerate(candidate_result.get("money_flows", []), start=1):
        flows.append({"id": f"MF-VALIDATION-{index}", **flow})
    return {
        "schema": DELIVERY_SCHEMA,
        "run": {"report_date": report_date, "coverage": "1 candidat", "summary": "Validation batch unitaire"},
        "opportunities": [{key: candidate_result[key] for key in ("source_id", "status", "reason", "facts")}],
        "money_flows": flows,
    }


def assemble_delivery(
    motor_input: dict[str, Any], results: Any, source_by_custom_id: dict[str, str]
) -> tuple[dict[str, Any], dict[str, int]]:
    report_date = str(motor_input.get("report_date") or "indéterminée")
    by_source: dict[str, dict[str, Any]] = {}
    usage = {"input_tokens": 0, "output_tokens": 0}
    failures: list[str] = []
    for entry in results:
        custom_id = _field(entry, "custom_id")
        expected_source = source_by_custom_id.get(custom_id)
        result = _field(entry, "result", {})
        result_type = _field(result, "type")
        if expected_source is None:
            failures.append(f"résultat inattendu {custom_id}")
            continue
        if result_type != "succeeded":
            failures.append(
                f"{expected_source}:{result_type or 'unknown'} ({_batch_error_detail(result)})"
            )
            continue
        message = _field(result, "message", {})
        value = json.loads(_message_text(message))
        if not isinstance(value, dict) or value.get("source_id") != expected_source:
            failures.append(f"{expected_source}:source_id_mismatch")
            continue
        if value.get("facts", {}).get("signal_id") != expected_source:
            failures.append(f"{expected_source}:signal_id_mismatch")
            continue
        if not isinstance(value.get("facts", {}).get("operator_access"), dict):
            failures.append(f"{expected_source}:operator_access_missing")
            continue
        validate_delivery(_single_delivery(value, report_date))
        by_source[expected_source] = value
        message_usage = _field(message, "usage", {})
        usage["input_tokens"] += int(_field(message_usage, "input_tokens", 0) or 0)
        usage["output_tokens"] += int(_field(message_usage, "output_tokens", 0) or 0)
    expected_sources = list(source_by_custom_id.values())
    missing = [source for source in expected_sources if source not in by_source]
    if failures or missing:
        detail = ", ".join([*failures, *[f"{source}:missing" for source in missing]])
        raise ValueError(f"Batch incomplet ; la file n'est pas avancée : {detail}.")
    opportunities: list[dict[str, Any]] = []
    money_flows: list[dict[str, Any]] = []
    for candidate_index, source_id in enumerate(expected_sources, start=1):
        item = by_source[source_id]
        opportunities.append({key: item[key] for key in ("source_id", "status", "reason", "facts")})
        for flow_index, flow in enumerate(item.get("money_flows", []), start=1):
            money_flows.append({"id": f"MF-{candidate_index:02d}-{flow_index:02d}", **flow})
    counts = {status: sum(item["status"] == status for item in opportunities) for status in ("RETAINED", "DISCARDED", "UNRESOLVED")}
    total = len(opportunities)
    delivery = {
        "schema": DELIVERY_SCHEMA,
        "run": {
            "report_date": report_date,
            "coverage": f"{total}/{total} candidats traités indépendamment par Message Batch",
            "summary": f"{counts['RETAINED']} retenu(s), {counts['DISCARDED']} écarté(s), {counts['UNRESOLVED']} non résolu(s).",
        },
        "opportunities": opportunities,
        "money_flows": money_flows,
    }
    validate_delivery(delivery)
    return delivery, usage


def _state_from_batch(batch: Any, input_hash: str, model: str, request_count: int) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "schema": STATE_SCHEMA,
        "input_sha256": input_hash,
        "model": model,
        "batch_id": _field(batch, "id"),
        "processing_status": _field(batch, "processing_status"),
        "request_count": request_count,
        "request_counts": _request_counts(batch),
        "ready": False,
        "created_at_utc": str(_field(batch, "created_at") or now),
        "updated_at_utc": now,
    }


def _load_reusable_state(path: Path, input_hash: str, model: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    state = _read_json(path)
    if state.get("schema") != STATE_SCHEMA:
        raise ValueError("État de batch Anthropic invalide.")
    if state.get("input_sha256") == input_hash and state.get("model") == model and state.get("batch_id"):
        return state
    if state.get("processing_status") != "ended":
        raise ValueError("Un autre batch Anthropic est encore en cours ; refus de mélanger deux lots.")
    return None


def run_batch(
    motor_input: dict[str, Any], *, client: Any, state_path: Path, output_path: Path,
    model: str = DEFAULT_MODEL, wait_seconds: int = 180, poll_seconds: int = 10,
) -> dict[str, Any]:
    requests, source_by_custom_id = build_requests(motor_input, model)
    input_hash = _canonical_hash(motor_input)
    previous = _load_reusable_state(state_path, input_hash, model)
    if previous:
        batch = client.messages.batches.retrieve(previous["batch_id"])
    else:
        batch = client.messages.batches.create(requests=requests)
    state = _state_from_batch(batch, input_hash, model, len(requests))
    _write_json(state_path, state)
    deadline = time.monotonic() + max(0, wait_seconds)
    while state["processing_status"] != "ended" and time.monotonic() < deadline:
        time.sleep(max(1, poll_seconds))
        batch = client.messages.batches.retrieve(state["batch_id"])
        state = _state_from_batch(batch, input_hash, model, len(requests))
        _write_json(state_path, state)
    if state["processing_status"] != "ended":
        return state
    try:
        delivery, usage = assemble_delivery(
            motor_input, client.messages.batches.results(state["batch_id"]), source_by_custom_id
        )
    except Exception as error:
        state.update({"ready": False, "error": f"{type(error).__name__}: {error}", "updated_at_utc": datetime.now(UTC).isoformat()})
        _write_json(state_path, state)
        raise
    _write_json(output_path, delivery)
    state.update({"ready": True, "usage": usage, "updated_at_utc": datetime.now(UTC).isoformat()})
    _write_json(state_path, state)
    return state


def _make_client(api_key: str) -> Any:
    try:
        from anthropic import Anthropic
    except ImportError as error:
        raise RuntimeError("Le SDK officiel Anthropic est requis.") from error
    return Anthropic(api_key=api_key, max_retries=2, timeout=60.0)


def _write_github_output(state: dict[str, Any]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(f"ready={'true' if state.get('ready') else 'false'}\n")
        handle.write(f"batch_id={state.get('batch_id', '')}\n")
        handle.write(f"processing_status={state.get('processing_status', '')}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--wait-seconds", type=int, default=180)
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY absent : aucun batch n'a été soumis.")
    state = run_batch(
        _read_json(args.input), client=_make_client(key), state_path=args.state,
        output_path=args.output, model=args.model, wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
    )
    _write_github_output(state)
    print(json.dumps({key: state.get(key) for key in ("batch_id", "processing_status", "request_counts", "ready")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
