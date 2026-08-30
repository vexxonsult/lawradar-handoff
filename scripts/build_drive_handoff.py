#!/usr/bin/env python3
"""Construit l'inbox Drive de preuves primaires, sans aucune interprétation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads((args.evidence / "manifest.json").read_text(encoding="utf-8"))
    documents = []
    for identifier in manifest["documents_found"]:
        document_path = args.evidence / "documents" / f"{identifier}.json"
        document = json.loads(document_path.read_text(encoding="utf-8"))
        if document.get("interpretation") is not None:
            raise ValueError(f"La preuve {identifier} contient une interprétation.")
        documents.append(document)
    handoff = {
        "schema": "lawradar-primary-handoff-v1",
        "purpose": "Preuves primaires brutes destinées à la couche surveillance ; aucune interprétation.",
        "manifest": manifest,
        "documents": documents,
        "interpretation": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
