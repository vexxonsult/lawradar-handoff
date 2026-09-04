#!/usr/bin/env python3
"""Client externe Entrepreneur, lecteur du signal universel LawRadar V2.

Le noyau LawRadar ne charge jamais ce module. Ce client lit un seul snapshot V2,
ne le modifie pas et écrit une livraison indépendante. Un appel Claude est
explicite (``--run-claude``) et ne peut avoir lieu que si le signal a franchi
les filtres déterministes et la porte opérateur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CORE_SCHEMA = "lawradar-universal-signal-v2"
CLIENT_SCHEMA = "lawradar-client-entrepreneur-delivery-v1"
SUPPORT_AGENTS = ("press", "demand", "market")
TERMINAL_STATUSES = {"COMPLETED", "NO_EVIDENCE"}
# Le workflow moteur et ses clients partagent le même modèle actif. Le choix
# reste surchargeable avec --model pour rejouer une livraison historique.
DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Tu es l'agent Entrepreneur, client externe de LawRadar.
Analyse exclusivement le JSON transmis : aucune recherche, aucun outil, aucun
contact et aucune affirmation non présente dans ces données. Le signal a déjà
passé les filtres déterministes. Propose UNE offre d'apport d'affaires B2B
réversible et légale, sans vendre ni distribuer de produit réglementé.

Retourne seulement le JSON imposé. La décision est TEST. Une commission n'est
possible que si son assiette chiffrée est explicitement dans les données : taux
entre 5 et 10 %, et montant de commission calculé à partir de cette assiette.
Sans assiette, mets les trois montants de commission à null et explique-le.
Le premier pas est gratuit, non exécuté, limité à 7 jours et réversible.
Chaque URL citée doit appartenir à la liste `allowed_source_urls` transmise."""

ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision",
        "axis_strategic",
        "offer",
        "commission_recommendation",
        "first_step_protocol",
        "source_urls",
    ],
    "properties": {
        "decision": {"type": "string", "enum": ["TEST"]},
        "axis_strategic": {"type": "string", "minLength": 1, "maxLength": 500},
        "offer": {
            "type": "object",
            "additionalProperties": False,
            "required": ["service", "target_actor", "provider_actor", "evidence_summary"],
            "properties": {
                "service": {"type": "string", "minLength": 1, "maxLength": 500},
                "target_actor": {"type": "string", "minLength": 1, "maxLength": 300},
                "provider_actor": {"type": ["string", "null"], "maxLength": 300},
                "evidence_summary": {"type": "string", "minLength": 1, "maxLength": 750},
            },
        },
        "commission_recommendation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["rate_percent", "base_amount_eur", "estimated_success_fee_eur", "conditions"],
            "properties": {
                "rate_percent": {"type": ["number", "null"], "minimum": 5, "maximum": 10},
                "base_amount_eur": {"type": ["number", "null"], "minimum": 0},
                "estimated_success_fee_eur": {"type": ["number", "null"], "minimum": 0},
                "conditions": {"type": "string", "minLength": 1, "maxLength": 500},
            },
        },
        "first_step_protocol": {
            "type": "object",
            "additionalProperties": False,
            "required": ["hypothesis", "draft_action", "success_signal", "stop_condition", "max_duration_days"],
            "properties": {
                "hypothesis": {"type": "string", "minLength": 1, "maxLength": 500},
                "draft_action": {"type": "string", "minLength": 1, "maxLength": 500},
                "success_signal": {"type": "string", "minLength": 1, "maxLength": 500},
                "stop_condition": {"type": "string", "minLength": 1, "maxLength": 500},
                "max_duration_days": {"type": "integer", "minimum": 1, "maximum": 7},
            },
        },
        "source_urls": {
            "type": "array",
            "items": {"type": "string", "format": "uri"},
            "maxItems": 8,
        },
    },
}


def source_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    """Read exactly one client input; this function never writes to ``path``."""
    raw = path.read_bytes()
    snapshot = json.loads(raw)
    if not isinstance(snapshot, dict) or snapshot.get("schema") != CORE_SCHEMA:
        raise ValueError("Le client Entrepreneur attend un lawradar-universal-signal-v2.")
    return snapshot, source_hash(raw)


def select_signal(snapshot: dict[str, Any], signal_id: str) -> dict[str, Any]:
    matches = [item for item in snapshot.get("signals", []) if isinstance(item, dict) and item.get("id") == signal_id]
    if len(matches) != 1:
        raise ValueError("Le signal client est absent ou dupliqué.")
    return matches[0]


def _collect_urls(value: Any) -> list[str]:
    """Collect source URLs already present in the core snapshot, never inventing one."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"url", "source_url", "canonical_url"} and isinstance(child, str) and child.startswith(("https://", "http://")):
                found.append(child)
            found.extend(_collect_urls(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_collect_urls(child))
    return list(dict.fromkeys(found))


def _collect_euro_amounts(value: Any, key_hint: str = "") -> list[float]:
    """Find only explicitly structured EUR amounts; free prose is deliberately ignored."""
    amounts: list[float] = []
    if isinstance(value, dict):
        for key, child in value.items():
            amounts.extend(_collect_euro_amounts(child, key.lower()))
    elif isinstance(value, list):
        for child in value:
            amounts.extend(_collect_euro_amounts(child, key_hint))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "eur" in key_hint or "euro" in key_hint or "montant" in key_hint or "amount" in key_hint:
            amounts.append(float(value))
    return list(dict.fromkeys(amounts))


def _compact_client_input(signal: dict[str, Any]) -> dict[str, Any]:
    """Expose only the selected signal and its proven support, keeping prompt cost bounded."""
    allowed_urls = _collect_urls(signal)
    return {
        "signal_id": signal.get("id"),
        "source": signal.get("source"),
        "radar": signal.get("radar"),
        "facts": signal.get("facts") or signal.get("opportunity_facts"),
        "deterministic_filters": signal.get("deterministic_filters"),
        "enrichments": signal.get("enrichments"),
        "allowed_source_urls": allowed_urls,
        "available_amounts_eur": _collect_euro_amounts(signal),
    }


def build_delivery(snapshot: dict[str, Any], snapshot_sha256: str, signal_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Build a zero-cost preflight delivery. It never invokes a model."""
    signal = select_signal(snapshot, signal_id)
    support = signal.get("enrichments") if isinstance(signal.get("enrichments"), dict) else {}
    statuses = {agent: (support.get(agent) or {}).get("status") for agent in SUPPORT_AGENTS}
    gate = signal.get("deterministic_filters") if isinstance(signal.get("deterministic_filters"), dict) else None
    access = gate.get("operator_access") if isinstance(gate, dict) and isinstance(gate.get("operator_access"), dict) else None
    gaps: list[str] = []
    skipped = False
    if signal.get("radar", {}).get("status") != "RETAINED":
        gaps.append("Le Radar n'a pas retenu ce signal.")
        skipped = True
    if not gate:
        gaps.append("Snapshot des filtres déterministes absent de l'export V2.")
    elif gate.get("final_constraint") != "PASS":
        gaps.append("Les filtres déterministes ne sont pas à PASS.")
        skipped = True
    if not access:
        gaps.append("La porte opérateur est absente de l'export V2.")
    elif access.get("status") not in {"PASS", "NOT_APPLICABLE"} or access.get("allow_external_collection") is not True:
        gaps.append("La porte opérateur ne confirme pas un accès B2B autorisé.")
        skipped = True
    incomplete = [agent for agent, status in statuses.items() if status not in TERMINAL_STATUSES]
    if incomplete:
        gaps.append("Enrichissements amont non terminés : " + ", ".join(sorted(incomplete)) + ".")
    positive = [agent for agent in ("demand", "market") if statuses[agent] == "COMPLETED"]
    if not positive:
        gaps.append("Aucune observation Demande ou Marché positive et terminale.")
    ready = not gaps
    status = "READY_FOR_AI_ASSESSMENT" if ready else ("SKIPPED" if skipped else "UNRESOLVED")
    return {
        "schema": CLIENT_SCHEMA,
        "client": "entrepreneur",
        "source_schema": CORE_SCHEMA,
        "source_sha256": snapshot_sha256,
        "signal_id": signal_id,
        "generated_at_utc": (now or datetime.now(UTC)).isoformat(),
        "status": status,
        "business_assessment": None,
        "gaps": gaps,
        "input_summary": {"support_statuses": statuses, "eligible_support": positive},
        "execution": {"external_calls": 0, "writes_to_core": False, "prompt_version": "embedded-v2"},
    }


def _message_text(message: Any) -> str:
    blocks = getattr(message, "content", None)
    if isinstance(message, dict):
        blocks = message.get("content")
    for block in blocks or []:
        block_type = getattr(block, "type", None) if not isinstance(block, dict) else block.get("type")
        if block_type == "text":
            text = getattr(block, "text", None) if not isinstance(block, dict) else block.get("text")
            if isinstance(text, str):
                return text
    raise ValueError("La réponse Claude ne contient aucun bloc texte JSON.")


def _message_field(message: Any, name: str, default: Any = None) -> Any:
    return message.get(name, default) if isinstance(message, dict) else getattr(message, name, default)


def _validate_assessment(assessment: Any, allowed_urls: list[str], allowed_amounts: list[float]) -> dict[str, Any]:
    """Apply invariants that remain true even if a model response is malformed."""
    if not isinstance(assessment, dict) or assessment.get("decision") != "TEST":
        raise ValueError("La décision client doit être TEST.")
    urls = assessment.get("source_urls")
    if not isinstance(urls, list) or any(not isinstance(url, str) or url not in allowed_urls for url in urls):
        raise ValueError("La réponse cite une URL absente du signal source.")
    recommendation = assessment.get("commission_recommendation")
    if not isinstance(recommendation, dict):
        raise ValueError("La recommandation de commission est absente.")
    rate = recommendation.get("rate_percent")
    base = recommendation.get("base_amount_eur")
    fee = recommendation.get("estimated_success_fee_eur")
    if rate is None or base is None or fee is None:
        if any(value is not None for value in (rate, base, fee)):
            raise ValueError("Les champs de commission doivent être tous renseignés ou tous nuls.")
    else:
        if not isinstance(rate, (int, float)) or not 5 <= rate <= 10:
            raise ValueError("Le taux de commission doit être entre 5 % et 10 %.")
        if not isinstance(base, (int, float)) or not any(abs(float(base) - amount) < 0.01 for amount in allowed_amounts):
            raise ValueError("L'assiette de commission n'est pas un montant sourcé du signal.")
        if not isinstance(fee, (int, float)) or abs(float(fee) - float(base) * float(rate) / 100) > 0.02:
            raise ValueError("Le montant de commission ne correspond pas à l'assiette et au taux.")
    protocol = assessment.get("first_step_protocol")
    if not isinstance(protocol, dict) or not isinstance(protocol.get("max_duration_days"), int) or not 1 <= protocol["max_duration_days"] <= 7:
        raise ValueError("Le premier pas doit être limité à sept jours.")
    return assessment


def _make_anthropic_client(api_key: str) -> Any:
    try:
        from anthropic import Anthropic
    except ImportError as error:
        raise RuntimeError("Le SDK Anthropic est requis : installez `anthropic` dans l'environnement d'exécution.") from error
    return Anthropic(api_key=api_key)


def run_claude_assessment(
    snapshot: dict[str, Any],
    snapshot_sha256: str,
    signal_id: str,
    *,
    client: Any | None = None,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run one bounded Claude call only after the deterministic zero-cost gate."""
    delivery = build_delivery(snapshot, snapshot_sha256, signal_id, now=now)
    if delivery["status"] != "READY_FOR_AI_ASSESSMENT":
        # Explicitly identify that no provider request was made for a closed signal.
        delivery["status"] = "SKIPPED" if delivery["status"] in {"SKIPPED", "UNRESOLVED"} else delivery["status"]
        return delivery

    signal = select_signal(snapshot, signal_id)
    client_input = _compact_client_input(signal)
    if client is None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            delivery["status"] = "FAILED"
            delivery["failure"] = "ANTHROPIC_API_KEY absent : aucun appel Claude n'a été lancé."
            return delivery
        client = _make_anthropic_client(key)

    try:
        message = client.messages.create(
            model=model,
            # Claude Sonnet 5 only accepts default sampling.  A business
            # recommendation needs some structured reasoning, but medium
            # effort remains deliberately bounded for this external client.
            max_tokens=2200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(client_input, ensure_ascii=False, separators=(",", ":"))}],
            thinking={"type": "adaptive"},
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": ASSESSMENT_SCHEMA}},
        )
        assessment = json.loads(_message_text(message))
        assessment = _validate_assessment(assessment, client_input["allowed_source_urls"], client_input["available_amounts_eur"])
    except Exception as error:  # API, transport, schema or model output error: core remains untouched.
        delivery["status"] = "FAILED"
        delivery["failure"] = f"Évaluation Claude non produite : {type(error).__name__}."
        delivery["execution"] = {
            "external_calls": 1,
            "writes_to_core": False,
            "provider": "anthropic",
            "model": model,
            "prompt_version": "embedded-v2",
        }
        return delivery

    usage = _message_field(message, "usage", {})
    delivery.update({"status": "COMPLETED", "business_assessment": assessment, "gaps": []})
    delivery["execution"] = {
        "external_calls": 1,
        "writes_to_core": False,
        "provider": "anthropic",
        "model": model,
        "message_id": _message_field(message, "id"),
        "input_tokens": _message_field(usage, "input_tokens"),
        "output_tokens": _message_field(usage, "output_tokens"),
        "prompt_version": "embedded-v2",
    }
    return delivery


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="out/universal-signal.json en lecture seule")
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="out/client-entrepreneur-delivery.json")
    parser.add_argument("--run-claude", action="store_true", help="autorise l'unique appel Claude après les garde-barrières")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"modèle Anthropic (défaut : {DEFAULT_MODEL})")
    parser.add_argument("--print-prompt", action="store_true")
    args = parser.parse_args()
    if args.print_prompt:
        print(SYSTEM_PROMPT)
        return 0
    if args.input.resolve() == args.output.resolve():
        raise ValueError("La sortie client doit être distincte du signal universel source.")
    snapshot, digest = read_snapshot(args.input)
    delivery = (
        run_claude_assessment(snapshot, digest, args.signal_id, model=args.model)
        if args.run_claude
        else build_delivery(snapshot, digest, args.signal_id)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(delivery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
