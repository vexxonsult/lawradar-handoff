#!/usr/bin/env python3
"""Reconstitue un noyau client temporaire depuis des signaux archivés.

Le noyau de production reste immuable : ce script ne l'écrit jamais. Il lit
uniquement des archives universelles V2 et rassemble une liste *explicite* de
signaux pour un rejeu Presse / Demande / Marché. Il sert aux enquêtes techniques
différées, dont le dossier universel courant ne contient plus forcément le
signal d'origine.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CORE_SCHEMA = "lawradar-universal-signal-v2"


def _archive_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.json") if not path.name.endswith(".manifest.json"))


def build(archive_root: Path, signal_ids: list[str], *, now: datetime | None = None) -> dict[str, Any]:
    """Return an immutable-facts replay core for exactly ``signal_ids``.

    Later archive files win only when the same signal identifier is present
    twice. This is deterministic and does not merge or rewrite source facts.
    """
    requested = list(dict.fromkeys(signal_ids))
    if not requested:
        raise ValueError("Au moins un signal d'enquête doit être demandé.")
    wanted = set(requested)
    found: dict[str, tuple[dict[str, Any], str]] = {}
    for path in _archive_files(archive_root):
        try:
            dossier = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as caught:
            raise ValueError(f"Archive universelle illisible : {path}") from caught
        if dossier.get("schema") != CORE_SCHEMA:
            continue
        for signal in dossier.get("signals", []):
            if not isinstance(signal, dict) or signal.get("id") not in wanted:
                continue
            if signal.get("radar", {}).get("status") != "RETAINED":
                raise ValueError(f"Le signal demandé n'est pas retenu : {signal.get('id')}")
            if not isinstance(signal.get("opportunity_facts"), dict):
                raise ValueError(f"Le signal demandé ne possède pas de faits versionnés : {signal.get('id')}")
            found[signal["id"]] = (copy.deepcopy(signal), path.as_posix())

    missing = [signal_id for signal_id in requested if signal_id not in found]
    if missing:
        raise ValueError("Signal(s) d'enquête introuvable(s) dans les archives : " + ", ".join(missing))

    selected = [found[signal_id][0] for signal_id in requested]
    provenance = {signal_id: found[signal_id][1] for signal_id in requested}
    fingerprint = hashlib.sha256(
        json.dumps({"signal_ids": requested, "archives": provenance}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    generated = now or datetime.now(UTC)
    return {
        "schema": CORE_SCHEMA,
        "run": {
            "id": f"investigation-replay:{fingerprint}",
            "kind": "ARCHIVED_FACTS_REPLAY",
            "generated_at_utc": generated.isoformat(),
            "purpose": "TECHNICAL_ENRICHMENT_RETRY",
            "archive_provenance": provenance,
        },
        "signals": selected,
        "money_flows": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--signal-id", action="append", dest="signal_ids", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.archive_root, args.signal_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
