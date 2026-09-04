#!/usr/bin/env python3
"""Publie l'état et la capacité par batch de la file moteur, sans IA."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


SCHEMA = "lawradar-motor-backlog-v1"
DEFAULT_BATCH_CAPACITY = 250


def build(queue: dict[str, Any], batch_capacity: int) -> dict[str, Any]:
    pending = queue.get("pending")
    processed = queue.get("processed")
    if not isinstance(pending, list) or not isinstance(processed, list):
        raise ValueError("File moteur invalide.")
    if batch_capacity < 1:
        raise ValueError("Capacité de batch invalide.")
    pending_count = len(pending)
    return {
        "schema": SCHEMA,
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "batch_capacity": batch_capacity,
        "capacity_window": "PER_BATCH",
        "pending_count": pending_count,
        "processed_count": len(processed),
        "status": "BACKLOG" if pending_count else "CLEAR",
        "next_action": (
            "RESUME_NEXT_BATCH_WINDOW"
            if pending_count
            else "NO_ACTION"
        ),
        "interpretation": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-capacity", type=int, default=DEFAULT_BATCH_CAPACITY)
    args = parser.parse_args()
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    args.output.write_text(
        json.dumps(build(queue, args.batch_capacity), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
