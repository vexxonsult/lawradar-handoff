#!/usr/bin/env python3
"""Compare deux livraisons de preuves et produit un delta sans interprétation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

FILES = (
    "primary-evidence-latest.json", "jorf-summaries-latest.json",
    "eurlex-oj-latest.json", "consultdd-latest.json", "status-latest.json",
)
VOLATILE_KEYS = {"collected_at_utc", "created_at_utc", "generated_at_utc"}


def stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [stable(item) for item in value]
    return value


def digest(payload: Any) -> str:
    encoded = json.dumps(stable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(directory: Path, name: str) -> Any | None:
    path = directory / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def count_items(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    if isinstance(payload.get("documents"), list):
        return len(payload["documents"])
    if isinstance(payload.get("editions"), list):
        return sum(len(edition.get("documents", [])) for edition in payload["editions"] if isinstance(edition, dict))
    if isinstance(payload.get("results"), list):
        return len(payload["results"])
    return 0


def build_delta(previous: Path, current: Path) -> dict[str, Any]:
    sources = []
    for name in FILES:
        before, after = read_json(previous, name), read_json(current, name)
        if after is None:
            status = "MISSING"
        elif before is None:
            status = "NEW"
        elif digest(before) == digest(after):
            status = "UNCHANGED"
        else:
            status = "CHANGED"
        sources.append({"file": name, "status": status, "item_count": count_items(after),
                        "sha256": digest(after) if after is not None else None, "interpretation": None})
    changed = [source["file"] for source in sources if source["status"] in {"NEW", "CHANGED"}]
    return {"schema": "lawradar-daily-delta-v1",
            "purpose": "Entrée courte pour la veille : changement mécanique des preuves, sans interprétation.",
            "sources": sources, "changed_sources": changed,
            "model_input_required": bool(changed), "interpretation": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build_delta(args.previous, args.current)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
