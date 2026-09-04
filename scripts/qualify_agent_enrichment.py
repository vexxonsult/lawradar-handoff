#!/usr/bin/env python3
"""Qualification Claude bornée d'un enrichissement Presse ou Marché.

Le script ne sait ni chercher sur le Web ni lire le noyau LawRadar. Il reçoit
un seul paquet déjà collecté, demande une conclusion JSON et laisse les
validateurs spécialisés rejeter toute source ou conclusion non traçable.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


PROMPTS = {
    "press": """Tu es l'agent Presse LawRadar. Analyse uniquement le JSON fourni.
N'utilise ni réseau, ni recherche, ni autre fichier. Retourne uniquement un JSON
lawradar-agent-enrichment-v1 pour agent=press. Respecte strictement le contrat
ci-dessous : toutes les URL de sources et décisions doivent être parmi les
candidats ; COMPLETED exige une ou plusieurs sources DIRECT ou CONTEXTUAL et
une synthèse avec renvois [1], [2] ; NO_EVIDENCE exige zéro source ; UNRESOLVED
exige une ambiguïté documentée. Ne crée jamais de source, chiffre ou fait absent.
details contient exactement signal_hash, window, queries, candidates_total,
candidates_after_dedup, coverage_level, decisions. Chaque décision contient
url, relevance (DIRECT|CONTEXTUAL|NOT_LINKED|AMBIGUOUS) et why_linked.""",
    "market": """Tu es l'agent Marché LawRadar. Analyse uniquement le JSON fourni.
N'utilise ni réseau, ni recherche, ni autre fichier. Retourne uniquement un JSON
lawradar-agent-enrichment-v1 pour agent=market. Toute URL de source ou conclusion
doit provenir des observations BOAMP reçues. N'affirme jamais une taille de marché,
un chiffre d'affaires ou une concurrence exhaustive. COMPLETED exige une ou plusieurs
sources pertinentes et une synthèse avec renvois [1], [2]. details contient exactement
signal_hash, collection_status, observations_total, conclusions. Chaque conclusion
contient url, interpretation (OFFER|ACTOR|CONSTRAINT|NOT_RELEVANT|AMBIGUOUS) et why.
En cas d'ambiguïté, retourne UNRESOLVED ; n'invente aucun fait.""",
}


def _text(message: Any) -> str:
    for block in getattr(message, "content", []):
        if getattr(block, "type", None) == "text" and isinstance(getattr(block, "text", None), str):
            return block.text
    raise ValueError("La réponse Claude ne contient aucun JSON texte.")


def qualify(payload: dict[str, Any], agent: str, *, client: Any, model: str) -> dict[str, Any]:
    if agent not in PROMPTS:
        raise ValueError("Agent de qualification inconnu.")
    message = client.messages.create(
        model=model,
        # Sonnet 5 rejects non-default sampling parameters.  The bounded
        # task uses adaptive thinking at low effort: enough to compare a few
        # traced sources, without paying for a long strategic analysis.
        max_tokens=2200,
        system=PROMPTS[agent],
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
    )
    result = json.loads(_text(message))
    if not isinstance(result, dict):
        raise ValueError("L'enrichissement Claude doit être un objet JSON.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=sorted(PROMPTS), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise ValueError("La sortie doit être distincte du paquet de qualification.")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY absente : qualification Claude non lancée.")
    try:
        from anthropic import Anthropic
    except ImportError as error:
        raise RuntimeError("Le SDK officiel anthropic est requis.") from error
    result = qualify(json.loads(args.input.read_text(encoding="utf-8")), args.agent, client=Anthropic(api_key=key), model=args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
