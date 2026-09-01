#!/usr/bin/env python3
"""Construit un registre lisible des derniers runs LawRadar."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != "lawradar-run-manifest-v1":
        raise ValueError("Manifeste d'exécution non pris en charge.")
    run = manifest.get("run")
    if not isinstance(run, dict):
        raise ValueError("Bloc run absent du manifeste.")
    kind = run.get("kind")
    if kind not in {"collector", "motor"}:
        raise ValueError("Type de run non pris en charge.")
    inputs = manifest.get("inputs", [])
    outputs = manifest.get("outputs", [])
    if not isinstance(inputs, list) or not isinstance(outputs, list):
        raise ValueError("Entrées ou sorties invalides dans le manifeste.")
    return {
        "kind": kind,
        "status": run.get("status"),
        "run_id": run.get("id"),
        "run_url": run.get("url"),
        "workflow": run.get("workflow"),
        "commit": run.get("commit"),
        "created_at_utc": run.get("created_at_utc"),
        "duration_seconds": run.get("duration_seconds"),
        "inputs": {"count": len(inputs), "missing": sum(not item.get("exists", False) for item in inputs if isinstance(item, dict))},
        "outputs": {"count": len(outputs), "missing": sum(not item.get("exists", False) for item in outputs if isinstance(item, dict))},
        "cost": manifest.get("cost_estimate", {}),
        "errors": manifest.get("errors", []),
        "retries": manifest.get("retries", 0),
    }


def build_index(paths: list[Path]) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        runs.append(summarize_manifest(manifest))
    runs.sort(key=lambda item: str(item.get("created_at_utc") or ""), reverse=True)
    return {
        "schema": "lawradar-run-index-v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "Registre technique des derniers runs, sans interprétation des preuves.",
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifests", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_index(args.manifests), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
