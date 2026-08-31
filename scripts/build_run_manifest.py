#!/usr/bin/env python3
"""Construit un manifeste d'exécution vérifiable pour un run GitHub Actions."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


def file_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return record
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    record.update({"bytes": path.stat().st_size, "sha256": digest})
    return record


def build_manifest(kind: str, status: str, inputs: list[Path], outputs: list[Path]) -> dict[str, Any]:
    now = int(time.time())
    started = os.environ.get("LAWRADAR_STARTED_AT")
    duration = max(0, now - int(started)) if started and started.isdigit() else None
    run_id = os.environ.get("GITHUB_RUN_ID")
    return {
        "schema": "lawradar-run-manifest-v1",
        "run": {
            "id": run_id,
            "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "kind": kind,
            "status": status,
            "workflow": os.environ.get("GITHUB_WORKFLOW"),
            "commit": os.environ.get("GITHUB_SHA"),
            "url": os.environ.get("GITHUB_SERVER_URL", "https://github.com") + "/" + os.environ.get("GITHUB_REPOSITORY", "") + "/actions/runs/" + (run_id or ""),
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "duration_seconds": duration,
        },
        "inputs": [file_record(path) for path in inputs],
        "outputs": [file_record(path) for path in outputs],
        "cost_estimate": {
            "status": "not_reported_by_provider",
            "model": os.environ.get("LAWRADAR_MODEL"),
            "note": "Le fournisseur ne publie pas le détail des tokens dans ce run ; la durée et le nombre d'appels restent mesurés.",
        },
        "errors": [],
        "retries": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--inputs", type=Path, nargs="*", default=[])
    parser.add_argument("--outputs", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_manifest(args.kind, args.status, args.inputs, args.outputs), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
