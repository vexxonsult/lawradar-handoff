#!/usr/bin/env python3
"""Prépare la seule entrée autorisée de l'agent Entrepreneur."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SUPPORT_AGENTS = ("press", "demand", "market")


def signal_hash(signal: dict[str, Any]) -> str:
    raw = json.dumps(signal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_signal(dossier: dict[str, Any], signal_id: str) -> dict[str, Any]:
    if dossier.get("schema") != "lawradar-universal-signal-v1":
        raise ValueError("Dossier universel non pris en charge.")
    matches = [item for item in dossier.get("signals", []) if item.get("id") == signal_id]
    if len(matches) != 1 or matches[0].get("radar", {}).get("status") != "RETAINED":
        raise ValueError("L'agent Entrepreneur ne traite qu'un signal RETAINED unique.")
    return matches[0]


def source_urls(value: Any) -> set[str]:
    urls: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"url", "source_url"} and isinstance(item, str) and item.startswith(("http://", "https://")):
                urls.add(item)
            else:
                urls.update(source_urls(item))
    elif isinstance(value, list):
        for item in value:
            urls.update(source_urls(item))
    return urls


def build(dossier: dict[str, Any], signal_id: str) -> dict[str, Any]:
    signal = select_signal(dossier, signal_id)
    enrichments = signal.get("enrichments", {})
    support = {}
    for agent in SUPPORT_AGENTS:
        slot = enrichments.get(agent, {"status": "PENDING", "result": None})
        support[agent] = {"status": slot.get("status"), "result": slot.get("result")}
    allowed = source_urls(signal.get("source")) | source_urls(dossier.get("money_flows", [])) | source_urls(support)
    return {
        "schema": "lawradar-entrepreneur-input-v1",
        "signal_id": signal_id,
        "signal_hash": signal_hash(signal),
        "signal": {"source": signal.get("source"), "radar": signal.get("radar")},
        "money_flows": dossier.get("money_flows", []),
        "support": support,
        "allowed_source_urls": sorted(allowed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.dossier.read_text(encoding="utf-8")), args.signal_id)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
