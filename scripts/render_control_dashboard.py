#!/usr/bin/env python3
"""Rend le tableau de contrôle LawRadar depuis un index de runs."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def tag(value: Any) -> str:
    return html.escape(str(value if value is not None else "Non communiqué"), quote=True)


def duration(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "Non mesurée"
    minutes, seconds = divmod(int(value), 60)
    return f"{minutes} min {seconds:02d} s" if minutes else f"{seconds} s"


def render_dashboard(index: dict[str, Any]) -> str:
    if index.get("schema") != "lawradar-run-index-v1" or not isinstance(index.get("runs"), list):
        raise ValueError("Index de runs non pris en charge.")
    rows = []
    for run in index["runs"]:
        if not isinstance(run, dict):
            raise ValueError("Run invalide dans l'index.")
        run_url = run.get("run_url")
        link = f'<a href="{tag(run_url)}">ouvrir le run</a>' if isinstance(run_url, str) and run_url else "lien indisponible"
        cost = run.get("cost", {})
        cost_status = cost.get("status") if isinstance(cost, dict) else "Non communiqué"
        rows.append(
            "<tr>"
            f"<td>{tag(run.get('kind'))}</td><td>{tag(run.get('status'))}</td>"
            f"<td>{tag(run.get('reason') or '—')}</td>"
            f"<td>{tag(run.get('created_at_utc'))}</td><td>{tag(duration(run.get('duration_seconds')))}</td>"
            f"<td>{tag(run.get('inputs', {}).get('count', 0))} / {tag(run.get('outputs', {}).get('count', 0))}</td>"
            f"<td>{tag(cost_status)}</td><td>{link}</td></tr>"
        )
    body = "".join(rows) or '<tr><td colspan="8">Aucun manifeste disponible.</td></tr>'
    return f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LawRadar — centre de contrôle</title>
<style>body{{font-family:system-ui,sans-serif;background:#f7f7f5;color:#1f2937;margin:0}}main{{max-width:1100px;margin:auto;padding:32px 20px}}header,section{{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:22px;margin-bottom:18px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px 8px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}}th{{font-size:.85rem;color:#4b5563}}a{{color:#0b63ce}}.note{{color:#4b5563}}</style>
</head><body><main><header><p class="note">Phase 4 — observabilité</p><h1>Centre de contrôle LawRadar</h1><p>Généré le {tag(index.get('generated_at_utc'))}. Ce tableau décrit les exécutions ; il n’interprète pas les preuves.</p></header>
<section><h2>Derniers runs</h2><table><thead><tr><th>Type</th><th>Statut</th><th>Raison</th><th>Horodatage UTC</th><th>Durée</th><th>Entrées / sorties</th><th>Coût</th><th>Détail</th></tr></thead><tbody>{body}</tbody></table></section>
</main></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    index = json.loads(args.input.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_dashboard(index), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
