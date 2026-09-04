#!/usr/bin/env python3
"""Exécute une branche client sur les signaux préautorisés, hors matrice GitHub.

Le plan client est un petit artefact immuable produit par le workflow. Chaque
signal est isolé dans son propre dossier de sortie ; les scripts existants
gardent leurs contrats et leurs validateurs, mais GitHub n'a plus à propager une
matrice dynamique entre jobs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> None:
    subprocess.run([sys.executable, *(str(ROOT / item) if item.startswith("scripts/") else item for item in args)], check=True)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objet JSON attendu : {path}")
    return value


def _allow(filters: Path) -> bool:
    return _load(filters).get("operator_access", {}).get("allow_external_collection") is True


def _press(core: Path, signal_id: str, target: Path, model: str) -> None:
    facts, filters = target / "opportunity-facts.json", target / "deterministic-filters.json"
    candidates, qualification, enrichment = target / "press-candidates.json", target / "press-qualification-input.json", target / "press-enrichment.json"
    _run("scripts/prepare_opportunity_facts.py", "--dossier", str(core), "--signal-id", signal_id, "--output", str(facts))
    _run("scripts/run_deterministic_filters.py", "--facts", str(facts), "--policy", "config/compliance-policy-v1.json", "--profile", "config/operator-profile-v1.json", "--output", str(filters))
    if not _allow(filters):
        raise ValueError(f"Collecte Presse interdite par la porte opérateur : {signal_id}")
    _run("scripts/collect_press_candidates.py", "--dossier", str(core), "--config", "config/press-agent-config.json", "--signal-id", signal_id, "--output", str(candidates))
    collected = _load(candidates)
    ready = bool(collected.get("candidates")) and collected.get("collection_successful", not collected.get("errors"))
    if ready:
        _run("scripts/prepare_press_qualification_input.py", "--dossier", str(core), "--candidates", str(candidates), "--output", str(qualification))
        _run("scripts/qualify_agent_enrichment.py", "--agent", "press", "--input", str(qualification), "--output", str(enrichment), "--model", model)
    else:
        _run("scripts/build_press_terminal_enrichment.py", "--candidates", str(candidates), "--output", str(enrichment))
    _run("scripts/validate_press_enrichment.py", "--candidates", str(candidates), "--enrichment", str(enrichment))


def _demand_market(core: Path, signal_id: str, target: Path, model: str) -> None:
    facts, filters = target / "opportunity-facts.json", target / "deterministic-filters.json"
    boamp, observations = target / "market-demand-boamp.json", target / "market-observations.json"
    demand, demand_enrichment = target / "demand-observations.json", target / "demand-enrichment.json"
    qualification, enrichment = target / "market-qualification-input.json", target / "market-enrichment.json"
    _run("scripts/prepare_opportunity_facts.py", "--dossier", str(core), "--signal-id", signal_id, "--output", str(facts))
    _run("scripts/run_deterministic_filters.py", "--facts", str(facts), "--policy", "config/compliance-policy-v1.json", "--profile", "config/operator-profile-v1.json", "--output", str(filters))
    if not _allow(filters):
        raise ValueError(f"Collecte BOAMP interdite par la porte opérateur : {signal_id}")
    _run("scripts/fetch_boamp_data.py", "--facts", str(facts), "--config", "config/boamp-collector-config-v1.json", "--output", str(boamp))
    _run("scripts/build_boamp_market_observations.py", "--facts", str(facts), "--boamp", str(boamp), "--output", str(observations))
    _run("scripts/build_boamp_demand_observations.py", "--facts", str(facts), "--boamp", str(boamp), "--output", str(demand))
    _run("scripts/build_boamp_demand_enrichment.py", "--observations", str(demand), "--output", str(demand_enrichment))
    _run("scripts/validate_demand_enrichment.py", "--observations", str(demand), "--enrichment", str(demand_enrichment))
    collected = _load(observations)
    ready = collected.get("collection_status") == "COMPLETED" and bool(collected.get("observations"))
    if ready:
        _run("scripts/prepare_market_qualification_input.py", "--facts", str(facts), "--observations", str(observations), "--output", str(qualification))
        _run("scripts/qualify_agent_enrichment.py", "--agent", "market", "--input", str(qualification), "--output", str(enrichment), "--model", model)
    else:
        _run("scripts/build_market_terminal_enrichment.py", "--observations", str(observations), "--output", str(enrichment))
    _run("scripts/validate_market_enrichment.py", "--observations", str(observations), "--enrichment", str(enrichment))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", choices=("press", "demand-market"), required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    args = parser.parse_args()
    plan = _load(args.plan)
    signals = plan.get("signals", [])
    if not isinstance(signals, list):
        raise ValueError("Plan client invalide : signals doit être une liste.")
    for item in signals:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("key"), str):
            raise ValueError("Plan client invalide : signal sans id ou clé.")
        target = args.output_root / item["key"]
        target.mkdir(parents=True, exist_ok=True)
        if args.branch == "press":
            _press(args.core, item["id"], target, args.model)
        else:
            _demand_market(args.core, item["id"], target, args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
