#!/usr/bin/env python3
"""Prépare l'unique entrée autorisée du modèle de qualification Presse."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:  # Supports both unit-test imports and standalone workflow execution.
    from scripts.collect_press_candidates import select_retained_signal
except ModuleNotFoundError:  # pragma: no cover - exercised by the workflow CLI.
    from collect_press_candidates import select_retained_signal


def build(
    dossier: dict[str, Any], candidates: dict[str, Any], *, allow_research_candidate: bool = False
) -> dict[str, Any]:
    signal = select_retained_signal(
        dossier, str(candidates.get("signal_id", "")), allow_research_candidate=allow_research_candidate
    )
    if candidates.get("schema") != "lawradar-press-candidates-v1":
        raise ValueError("Candidats Presse non pris en charge.")
    return {
        "schema": "lawradar-press-qualification-input-v1",
        "signal": {
            "id": signal.get("id"),
            "source": signal.get("source"),
            "radar": signal.get("radar"),
        },
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-research-candidate", action="store_true")
    args = parser.parse_args()
    result = build(
        json.loads(args.dossier.read_text(encoding="utf-8")),
        json.loads(args.candidates.read_text(encoding="utf-8")),
        allow_research_candidate=args.allow_research_candidate,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
