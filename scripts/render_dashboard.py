#!/usr/bin/env python3
"""Rend un dashboard HTML à partir d'un résultat moteur structuré.

Le script ne produit aucune interprétation : il met uniquement en page les
valeurs déjà décidées par le moteur. Il permet de ne plus transporter de long
HTML dans une exécution IA.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


REQUIRED_FLOW_FIELDS = {
    "label", "title", "money_sentence", "explanation", "payer", "recipient",
    "amount", "effective_date", "certainty", "next_action",
}


def validate_result(result: dict) -> None:
    if result.get("schema") != "lawradar-dashboard-input-v1":
        raise ValueError("Schéma de résultat moteur non pris en charge.")
    for field in ("report_date", "headline", "coverage"):
        if not isinstance(result.get(field), str):
            raise ValueError(f"Champ obligatoire invalide : {field}.")
    if not isinstance(result.get("flows"), list):
        raise ValueError("Champ obligatoire invalide : flows.")
    for index, flow in enumerate(result["flows"]):
        if not isinstance(flow, dict):
            raise ValueError(f"Flux {index} invalide.")
        missing = REQUIRED_FLOW_FIELDS - flow.keys()
        if missing:
            raise ValueError(f"Flux {index} incomplet : {', '.join(sorted(missing))}.")
        if any(not isinstance(flow[name], str) for name in REQUIRED_FLOW_FIELDS):
            raise ValueError(f"Flux {index} contient une valeur non textuelle.")


def tag(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_dashboard(result: dict) -> str:
    validate_result(result)
    cards = []
    for flow in result["flows"]:
        cards.append(
            "<article class=\"flow\">"
            f"<p class=\"badge\">{tag(flow['label'])}</p>"
            f"<h2>{tag(flow['title'])}</h2>"
            f"<p class=\"money\">{tag(flow['money_sentence'])}</p>"
            f"<p>{tag(flow['explanation'])}</p><dl>"
            f"<dt>Qui paie ?</dt><dd>{tag(flow['payer'])}</dd>"
            f"<dt>Qui reçoit ?</dt><dd>{tag(flow['recipient'])}</dd>"
            f"<dt>Combien ?</dt><dd>{tag(flow['amount'])}</dd>"
            f"<dt>À partir de quand ?</dt><dd>{tag(flow['effective_date'])}</dd>"
            f"<dt>Certitude</dt><dd>{tag(flow['certainty'])}</dd>"
            f"<dt>À faire</dt><dd>{tag(flow['next_action'])}</dd></dl></article>"
        )
    content = "\n".join(cards) or "<p>Aucun flux structuré ce passage.</p>"
    return f"""<!doctype html>
<html lang=\"fr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Money Flow Radar — {tag(result['report_date'])}</title>
<style>body{{font-family:system-ui,sans-serif;background:#f7f7f5;color:#1f2937;margin:0}}main{{max-width:900px;margin:auto;padding:32px 20px}}header{{border-bottom:1px solid #ddd;padding-bottom:20px}}.coverage,.badge{{display:inline-block;background:#fff3cd;border-radius:999px;padding:4px 10px;font-weight:600}}.flow{{background:white;border:1px solid #e5e7eb;border-radius:14px;padding:20px;margin:18px 0}}.money{{font-size:1.1rem;font-weight:650}}dt{{font-weight:650;margin-top:10px}}dd{{margin:2px 0}}</style>
</head><body><main><header><p class=\"coverage\">{tag(result['coverage'])}</p><h1>{tag(result['headline'])}</h1><p>{tag(result['report_date'])}</p></header><section><h2>Flux du jour</h2>{content}</section></main></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.input.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_dashboard(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
