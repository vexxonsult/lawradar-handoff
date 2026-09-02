#!/usr/bin/env python3
"""Client externe Entrepreneur : lecture seule du signal universel V2.

Ce programme ne fait pas partie du noyau LawRadar. Il consomme un export V2
sans le modifier et écrit exclusivement une livraison client indépendante.
L'appel éventuel à un modèle reste désactivé : `SYSTEM_PROMPT` est la consigne
versionnée à transmettre à un outil externe après validation humaine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CORE_SCHEMA = "lawradar-universal-signal-v2"
CLIENT_SCHEMA = "lawradar-client-entrepreneur-delivery-v1"
SUPPORT_AGENTS = ("press", "demand", "market")
TERMINAL_STATUSES = {"COMPLETED", "NO_EVIDENCE"}

SYSTEM_PROMPT = """Tu es un client externe de LawRadar, spécialiste d'apport
d'affaires B2B. Lis seulement le signal universel transmis. N'utilise aucun
réseau et n'invente ni montant, ni acteur, ni autorisation. Tu ne t'actives que
si les filtres sont PASS et la porte opérateur est PASS ou NOT_APPLICABLE ;
sinon tu retournes INVESTIGATE.
Propose au plus une offre B2B, une commission de 5 à 10 % seulement sur une
assiette chiffrée et sourcée, et un test gratuit, réversible et non exécuté.
Ne publie rien, ne contacte personne et ne modifie jamais le signal source."""


def source_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    """Read exactly one client input; this function never writes to `path`."""
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


def build_delivery(snapshot: dict[str, Any], snapshot_sha256: str, signal_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Prepare, but never execute, an external Entrepreneur assessment."""
    signal = select_signal(snapshot, signal_id)
    support = signal.get("enrichments") if isinstance(signal.get("enrichments"), dict) else {}
    statuses = {agent: (support.get(agent) or {}).get("status") for agent in SUPPORT_AGENTS}
    gate = signal.get("deterministic_filters") if isinstance(signal.get("deterministic_filters"), dict) else None
    access = gate.get("operator_access") if isinstance(gate, dict) and isinstance(gate.get("operator_access"), dict) else None
    gaps: list[str] = []
    if signal.get("radar", {}).get("status") != "RETAINED":
        gaps.append("Le Radar n'a pas retenu ce signal.")
    if not gate:
        gaps.append("Snapshot des filtres déterministes absent de l'export V2.")
    elif gate.get("final_constraint") != "PASS":
        gaps.append("Les filtres déterministes ne sont pas à PASS.")
    if not access or access.get("status") not in {"PASS", "NOT_APPLICABLE"} or access.get("allow_external_collection") is not True:
        gaps.append("La porte opérateur ne confirme pas un accès B2B autorisé.")
    incomplete = [agent for agent, status in statuses.items() if status not in TERMINAL_STATUSES]
    if incomplete:
        gaps.append("Enrichissements amont non terminés : " + ", ".join(sorted(incomplete)) + ".")
    positive = [agent for agent in ("demand", "market") if statuses[agent] == "COMPLETED"]
    if not positive:
        gaps.append("Aucune observation Demande ou Marché positive et terminale.")
    ready = not gaps
    return {
        "schema": CLIENT_SCHEMA,
        "client": "entrepreneur",
        "source_schema": CORE_SCHEMA,
        "source_sha256": snapshot_sha256,
        "signal_id": signal_id,
        "generated_at_utc": (now or datetime.now(UTC)).isoformat(),
        "status": "READY_FOR_AI_ASSESSMENT" if ready else "UNRESOLVED",
        "business_assessment": None,
        "gaps": gaps,
        "input_summary": {"support_statuses": statuses, "eligible_support": positive},
        "execution": {"external_calls": 0, "writes_to_core": False, "prompt_version": "embedded-v1"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="out/universal-signal.json en lecture seule")
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="out/client-entrepreneur-delivery.json")
    parser.add_argument("--print-prompt", action="store_true")
    args = parser.parse_args()
    if args.print_prompt:
        print(SYSTEM_PROMPT)
        return 0
    if args.input.resolve() == args.output.resolve():
        raise ValueError("La sortie client doit être distincte du signal universel source.")
    snapshot, digest = read_snapshot(args.input)
    delivery = build_delivery(snapshot, digest, args.signal_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(delivery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
