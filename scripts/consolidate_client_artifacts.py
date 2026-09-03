#!/usr/bin/env python3
"""Assemble les sorties Hub & Spoke sans modifier le signal universel du noyau."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

try:
    from scripts.merge_agent_enrichment import merge, validate_enrichment
except ModuleNotFoundError:  # pragma: no cover - exécution directe du workflow.
    from merge_agent_enrichment import merge, validate_enrichment


EXPECTED_AGENTS = {"press", "demand", "market"}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON objet attendu : {path}")
    return value


def discover(root: Path) -> list[dict[str, Any]]:
    """Charge uniquement les trois livraisons explicitement autorisées."""
    names = {"press-enrichment.json", "demand-enrichment.json", "market-enrichment.json"}
    enrichments: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(item for item in root.rglob("*.json") if item.name in names):
        enrichment = _read(path)
        validate_enrichment(enrichment)
        key = (enrichment["signal_id"], enrichment["agent"])
        if key in seen:
            raise ValueError(f"Livraison client dupliquée : {key[0]} / {key[1]}")
        seen.add(key)
        enrichments.append(enrichment)
    return enrichments


def consolidate(
    core: dict[str, Any],
    enrichments: list[dict[str, Any]],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if core.get("schema") != "lawradar-universal-signal-v2":
        raise ValueError("Le contexte client attend un signal universel V2.")
    if readiness.get("schema") != "lawradar-agent-pilot-readiness-v1":
        raise ValueError("Manifeste de préparation des clients invalide.")

    result = copy.deepcopy(core)
    filters_by_signal = {
        item.get("signal_id"): item.get("filters")
        for item in readiness.get("signals", [])
        if isinstance(item, dict) and isinstance(item.get("filters"), dict)
    }
    for signal in result.get("signals", []):
        if isinstance(signal, dict) and signal.get("id") in filters_by_signal:
            signal["deterministic_filters"] = filters_by_signal[signal["id"]]

    for enrichment in sorted(enrichments, key=lambda item: (item["signal_id"], item["agent"])):
        result = merge(result, enrichment)

    eligible = {
        item.get("signal_id")
        for item in readiness.get("signals", [])
        if isinstance(item, dict) and item.get("ready_for_pilots") is True
    }
    for signal in result.get("signals", []):
        if not isinstance(signal, dict) or signal.get("id") not in eligible:
            continue
        statuses = {
            agent: (signal.get("enrichments", {}).get(agent) or {}).get("status")
            for agent in EXPECTED_AGENTS
        }
        missing = sorted(agent for agent, status in statuses.items() if status == "PENDING")
        if missing:
            raise ValueError(
                f"Enrichissements clients manquants pour {signal.get('id')} : {', '.join(missing)}"
            )

    result["client_context"] = {
        "schema": "lawradar-client-context-v1",
        "core_immutable": True,
        "assembled_agents": sorted({item["agent"] for item in enrichments}),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = consolidate(_read(args.core), discover(args.artifacts), _read(args.readiness))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
