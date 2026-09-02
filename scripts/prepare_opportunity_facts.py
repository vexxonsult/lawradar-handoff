#!/usr/bin/env python3
"""Extrait les faits liés à un signal universel pour les collecteurs bornés."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.run_deterministic_filters import validate_facts
except ModuleNotFoundError:  # pragma: no cover - exercised by workflow CLI.
    from run_deterministic_filters import validate_facts


def extract(dossier: dict[str, Any], signal_id: str) -> dict[str, Any]:
    if dossier.get("schema") not in {"lawradar-universal-signal-v1", "lawradar-universal-signal-v2"}:
        raise ValueError("Dossier universel non pris en charge.")
    matches = [item for item in dossier.get("signals", []) if item.get("id") == signal_id]
    if len(matches) != 1 or matches[0].get("radar", {}).get("status") != "RETAINED":
        raise ValueError("Les faits ne peuvent être extraits que pour un signal RETAINED unique.")
    facts = matches[0].get("opportunity_facts")
    if not isinstance(facts, dict):
        raise ValueError("Le signal ne porte pas encore de faits d'opportunité.")
    validate_facts(facts)
    if facts.get("signal_id") != signal_id:
        raise ValueError("Faits d'opportunité rattachés au mauvais signal universel.")
    return facts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    facts = extract(json.loads(args.dossier.read_text(encoding="utf-8")), args.signal_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0
