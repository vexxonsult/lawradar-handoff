#!/usr/bin/env python3
"""Publie un paquet candidat seulement s'il apporte au moins une preuve primaire."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def promote(candidate: Path, candidate_evidence: Path, current: Path, current_evidence: Path, status: Path) -> bool:
    handoff = json.loads(candidate.read_text(encoding="utf-8"))
    documents = handoff.get("documents") or []
    promoted = bool(documents)

    status_payload = {
        "schema": "lawradar-public-handoff-status-v1",
        "promoted": promoted,
        "reason": "DOCUMENTS_FOUND" if promoted else "NO_TARGET_DOCUMENT_IN_LATEST_ARCHIVE",
        "candidate_manifest": handoff.get("manifest"),
        "interpretation": None,
    }
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps(status_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not promoted:
        return False

    if current_evidence.exists():
        shutil.rmtree(current_evidence)
    shutil.copytree(candidate_evidence, current_evidence)
    current.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, current)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-evidence", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--current-evidence", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    args = parser.parse_args()
    promote(args.candidate, args.candidate_evidence, args.current, args.current_evidence, args.status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
