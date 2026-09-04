#!/usr/bin/env python3
"""Prépare la seule entrée autorisée de qualification Marché."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build(facts: dict[str, Any], observations: dict[str, Any]) -> dict[str, Any]:
    if facts.get("schema") != "lawradar-opportunity-facts-v1":
        raise ValueError("Faits d'opportunité non pris en charge.")
    if observations.get("schema") != "lawradar-market-observations-v1":
        raise ValueError("Observations Marché non prises en charge.")
    if observations.get("signal_id") != facts.get("signal_id"):
        raise ValueError("Observations Marché rattachées à un autre signal.")
    return {
        "schema": "lawradar-market-qualification-input-v1",
        "signal_id": facts["signal_id"],
        "signal_hash": observations["signal_hash"],
        "facts": facts,
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        json.loads(args.facts.read_text(encoding="utf-8")),
        json.loads(args.observations.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
