#!/usr/bin/env python3
"""Publie l'état de capacité quotidienne de la file moteur, sans IA."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


SCHEMA = "lawradar-motor-backlog-v1"


def build(queue: dict[str, Any], daily_capacity: int) -> dict[str, Any]:
    pending = queue.get("pending")
    processed = queue.get("processed")
    if not isinstance(pending, list) or not isinstance(processed, list):
        raise ValueError("File moteur invalide.")
    if daily_capacity < 1:
        raise ValueError("Capacité quotidienne invalide.")
    pending_count = len(pending)
    return {
        "schema": SCHEMA,
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "daily_capacity": daily_capacity,
        "pending_count": pending_count,
        "processed_count": len(processed),
        "status": "BACKLOG" if pending_count else "CLEAR",
        "next_action": (
            "PRIORITIZE_PENDING_NEXT_DAILY_WINDOW"
            if pending_count
            else "NO_ACTION"
        ),
        "interpretation": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--daily-capacity", type=int, default=30)
    args = parser.parse_args()
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    args.output.write_text(
        json.dumps(build(queue, args.daily_capacity), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
