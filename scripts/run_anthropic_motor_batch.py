#!/usr/bin/env python3
"""Exécute le Moteur LawRadar avec l'API Message Batches d'Anthropic.

Chaque candidat devient une requête Messages indépendante. L'identifiant du
batch est conservé afin qu'un run ultérieur puisse reprendre le même travail
sans soumettre ni facturer une seconde fois le lot.
"""

from __future__ import annotations

import argparse
import copy
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
# Plafond de sûreté opérationnel, volontairement très inférieur à la limite
# fournisseur (100 000 requêtes / 256 Mo). Il permet néanmoins d'absorber en
# un seul lot les journées denses déjà observées par LawRadar.
MAX_CANDIDATES = 250
# Toute modification de la requête fournisseur doit produire un nouveau batch
# une fois le batch précédent achevé, sans jamais doubler un batch en cours.
BATCH_REQUEST_VERSION = "2026-09-04-readable-primary-review-v5"
_UNSUPPORTED_ANTHROPIC_SCHEMA_KEYWORDS = {
    "maxItems", "maxLength", "minLength", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern", "uniqueItems",
}

SYSTEM_PROMPT = """Tu es le moteur factuel LawRadar. Analyse uniquement le
candidat JSON fourni. Aucune recherche, aucun outil, aucune connaissance
externe. Toute information non démontrée reste null, MISSING, PARTIAL,
UNKNOWN ou UNRESOLVED selon le schéma. Ne déduis jamais un capital, un délai,
une autorisation, un acteur ou un flux financier. Un flux n'est admis que si
sa direction et ses acteurs sont explicitement étayés dans la preuve.

Le champ candidate.discovery est un signal de routage déterministe. Quel que
soit son statut, produis une lecture courte et pédagogique du texte dans
`reading` : conséquence concrète, acteurs concernés, bénéficiaires, parties
contraintes, partenaires de service éventuellement documentés et inconnues.
Ces champs doivent rester vides lorsqu'ils ne sont pas démontrés ; ne déduis
jamais un gagnant, un perdant, un marché ou une offre légale. Un texte
CONTEXT_REVIEW doit normalement être DISCARDED comme opportunité, mais sa
lecture reste utile au tableau quotidien. Vérifie toujours les preuves
officielles du candidat.

Routage Énergie / CEE : un texte français publié créant ou modifiant une fiche
d'opération standardisée CEE, une bonification CEE ou une obligation mesurable
d'efficacité énergétique ne doit pas être DISCARDED au seul motif qu'il relève
de l'énergie. S'il décrit un périmètre industriel ou professionnel identifiable,
retourne RETAINED, classe operator_access.sector à ENERGY_EFFICIENCY et décris
uniquement un service B2B non réglementé possible de veille, qualification de
besoin ou mise en relation avec un partenaire ; pour ce seul service, écris
direct_offer_status à ACCESSIBLE. Ne prétends jamais que LawRadar
peut installer l'équipement, obtenir des CEE, certifier une opération ou agir
au nom d'un obligé ; ces éléments restent MISSING ou UNKNOWN sans preuve.

Routage Médicaments : l'existence d'une liste d'établissements, de collectivités
ou de contacts n'est jamais une preuve de rôle périphérique légal ni de demande.
Ne transforme jamais une inscription au remboursement ou à l'agrément en marché
ou en autorisation de vendre, distribuer, promouvoir ou prescrire un médicament.
Retourne uniquement le JSON demandé, sans markdown."""


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

READING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "consequence", "affected_actors", "beneficiaries",
        "constrained_parties", "potential_service_partners", "unknowns",
    ],
    "properties": {
        "consequence": {"type": "string", "minLength": 1},
        "affected_actors": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1}},
        "beneficiaries": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1}},
        "constrained_parties": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1}},
        "potential_service_partners": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1}},
        "unknowns": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1}},
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
                "sector": {"type": "string", "enum": ["MEDICINES", "FINANCIAL_SERVICES", "LEGAL_SERVICES", "ENERGY_EFFICIENCY", "OTHER_REGULATED", "NOT_CLASSIFIED"]},
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
    "required": ["source_id", "status", "reason", "facts", "reading", "money_flows"],
    "properties": {
        "source_id": {"type": "string", "minLength": 1},
        "status": {"type": "string", "enum": ["RETAINED", "DISCARDED", "UNRESOLVED"]},
        "reason": {"type": "string", "minLength": 1},
        "facts": FACTS_SCHEMA,
        "reading": READING_SCHEMA,
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


def anthropic_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Retire seulement les contraintes non prises en charge par Anthropic.

    La validation locale conserve le schéma complet après réponse : le fournisseur
    contraint la structure, LawRadar contrôle les bornes et longueurs ensuite.
    """
    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: sanitize(item)
                for key, item in value.items()
                if key not in _UNSUPPORTED_ANTHROPIC_SCHEMA_KEYWORDS
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    return sanitize(copy.deepcopy(schema))


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
                # Le schéma comporte des objets imbriqués obligatoires. 1 800
                # tokens a tronqué une réponse valide avant sa dernière accolade
                # lors du premier batch réel. Le plafond n'est pas une longueur
                # cible : la sortie reste factuelle et la facturation porte sur
                # les tokens effectivement produits.
                "max_tokens": 4096,
                "system": SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
                }],
                "output_config": {
                    "format": {"type": "json_schema", "schema": anthropic_output_schema(CANDIDATE_RESULT_SCHEMA)}
                },
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
    # Le SDK enveloppe parfois l'erreur API dans un objet de type ``error``.
    # Descendre d'un niveau évite de perdre le type et le message utiles.
    nested = _field(error, "error", None)
    if nested is not None:
        error = nested
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
        "opportunities": [{key: candidate_result[key] for key in ("source_id", "status", "reason", "facts", "reading")}],
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
        raw_text = _message_text(message)
        try:
            value = json.loads(raw_text)
        except json.JSONDecodeError as error:
            # Le texte fournisseur n'est volontairement pas conservé : il
            # peut contenir du contenu officiel long. Ces métadonnées suffisent
            # pour distinguer une troncature d'une réponse mal formée.
            message_usage = _field(message, "usage", {})
            stop_reason = str(_field(message, "stop_reason", "unknown"))
            output_tokens = int(_field(message_usage, "output_tokens", 0) or 0)
            failures.append(
                f"{expected_source}:invalid_json"
                f"(stop={stop_reason},output_tokens={output_tokens},chars={len(raw_text)},at={error.pos})"
            )
            continue
        if not isinstance(value, dict) or value.get("source_id") != expected_source:
            failures.append(f"{expected_source}:source_id_mismatch")
            continue
        facts = value.get("facts")
        if not isinstance(facts, dict):
            failures.append(f"{expected_source}:facts_missing")
            continue
        # signal_id est une clé de jointure, pas une conclusion du modèle.
        # Le custom_id du batch garantit déjà l'association à la source : on
        # recopie donc systématiquement l'identifiant officiel vérifié.
        facts["signal_id"] = expected_source
        if not isinstance(facts.get("operator_access"), dict):
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
        opportunities.append({key: item[key] for key in ("source_id", "status", "reason", "facts", "reading")})
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


def _state_from_batch(batch: Any, request_hash: str, model: str, request_count: int) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "schema": STATE_SCHEMA,
        # ``input_sha256`` est conservé pour la compatibilité avec les états
        # déjà versionnés. Depuis les batches, l'identité utile est le contenu
        # réellement envoyé au fournisseur, pas les métadonnées du delta.
        "input_sha256": request_hash,
        "request_sha256": request_hash,
        "model": model,
        "request_version": BATCH_REQUEST_VERSION,
        "batch_id": _field(batch, "id"),
        "processing_status": _field(batch, "processing_status"),
        "request_count": request_count,
        "request_counts": _request_counts(batch),
        "ready": False,
        "created_at_utc": str(_field(batch, "created_at") or now),
        "updated_at_utc": now,
    }


def _load_reusable_state(
    path: Path, request_hash: str, model: str, request_count: int
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    state = _read_json(path)
    if state.get("schema") != STATE_SCHEMA:
        raise ValueError("État de batch Anthropic invalide.")
    state_hash = state.get("request_sha256", state.get("input_sha256"))
    if (
        state_hash == request_hash
        and state.get("model") == model
        and state.get("request_version") == BATCH_REQUEST_VERSION
        and state.get("batch_id")
    ):
        return state
    if state.get("processing_status") != "ended":
        # Migration sans perte : les états produits avant ``request_sha256``
        # ne permettent pas de recalculer l'ancienne empreinte. Pendant ce
        # premier passage, la file reste gelée sur le même nombre de candidats
        # et le batch existant est donc repris, puis réécrit au nouveau format.
        if (
            "request_sha256" not in state
            and state.get("model") == model
            and state.get("request_version") == BATCH_REQUEST_VERSION
            and state.get("request_count") == request_count
            and state.get("batch_id")
        ):
            return state

        # Un lot réellement différent ne doit ni être soumis en double ni faire
        # échouer le workflow. Il reste dans la file : le prochain passage
        # reprendra le batch actif, puis soumettra ce nouveau lot une fois le
        # précédent terminé.
        state.update({
            "ready": False,
            "deferred_reason": "ACTIVE_BATCH_DIFFERENT_REQUEST",
            "updated_at_utc": datetime.now(UTC).isoformat(),
        })
        _write_json(path, state)
        return state
    return None


def run_batch(
    motor_input: dict[str, Any], *, client: Any, state_path: Path, output_path: Path,
    model: str = DEFAULT_MODEL, wait_seconds: int = 180, poll_seconds: int = 10,
) -> dict[str, Any]:
    requests, source_by_custom_id = build_requests(motor_input, model)
    # Les métadonnées de collecte changent entre deux piges (sources exclues,
    # horodatages, etc.) sans modifier les candidats ni les requêtes Anthropic.
    # Hacher les requêtes protège donc le batch actif contre une fausse
    # différence d'entrée et évite une seconde soumission.
    request_hash = _canonical_hash(requests)
    previous = _load_reusable_state(state_path, request_hash, model, len(requests))
    if previous:
        if previous.get("deferred_reason") == "ACTIVE_BATCH_DIFFERENT_REQUEST":
            return previous
        batch = client.messages.batches.retrieve(previous["batch_id"])
    else:
        batch = client.messages.batches.create(requests=requests)
    state = _state_from_batch(batch, request_hash, model, len(requests))
    _write_json(state_path, state)
    deadline = time.monotonic() + max(0, wait_seconds)
    while state["processing_status"] != "ended" and time.monotonic() < deadline:
        time.sleep(max(1, poll_seconds))
        batch = client.messages.batches.retrieve(state["batch_id"])
        state = _state_from_batch(batch, request_hash, model, len(requests))
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
        # Un batch achevé mais invalide doit rester traçable : le workflow
        # versionne son état et ne le soumet pas une seconde fois par défaut.
        return state
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
