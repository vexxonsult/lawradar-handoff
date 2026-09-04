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
from datetime import UTC, datetime
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


def unresolved_enrichment(payload: dict[str, Any], agent: str, cause: str) -> dict[str, Any]:
    """Préserve un résultat exploitable si la réponse IA est vide ou invalide.

    Une indisponibilité du modèle n'est ni une absence de preuve, ni une panne
    de collecte. Elle doit donc rester une incertitude traçable qui n'interrompt
    pas les autres branches du workflow.
    """
    observed_at = datetime.now(UTC).isoformat()
    cause = " ".join(cause.split())[:240]
    if agent == "press":
        candidates = payload.get("candidates")
        if not isinstance(candidates, dict):
            raise ValueError("Entrée Presse invalide pour la sortie UNRESOLVED.")
        decisions = [
            {
                "url": item["url"],
                "relevance": "AMBIGUOUS",
                "why_linked": "La qualification IA n'a pas produit de réponse exploitable ; le lien n'est pas tranché.",
            }
            for item in candidates.get("candidates", [])
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"]
        ]
        if not decisions:
            raise ValueError("Aucun candidat Presse traçable pour la sortie UNRESOLVED.")
        return {
            "schema": "lawradar-agent-enrichment-v1",
            "agent": "press",
            "signal_id": candidates.get("signal_id"),
            "status": "UNRESOLVED",
            "observed_at_utc": observed_at,
            "summary": "La qualification Presse n'a pas produit de réponse exploitable ; aucun lien média n'est conclu.",
            "sources": [],
            "limitations": [f"Réponse Claude non exploitable : {cause}"],
            "details": {
                "signal_hash": candidates.get("signal_hash"),
                "window": candidates.get("window", {}),
                "queries": candidates.get("queries", []),
                "candidates_total": candidates.get("candidates_total", 0),
                "candidates_after_dedup": candidates.get("candidates_after_dedup", 0),
                "coverage_level": "NONE",
                "decisions": decisions,
            },
            "score": None,
        }
    if agent == "market":
        observations = payload.get("observations")
        if not isinstance(observations, dict):
            raise ValueError("Entrée Marché invalide pour la sortie UNRESOLVED.")
        conclusions = [
            {
                "url": item["url"],
                "interpretation": "AMBIGUOUS",
                "why": "La qualification IA n'a pas produit de réponse exploitable ; cette observation n'est pas interprétée.",
            }
            for item in observations.get("observations", [])
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"]
        ]
        if not conclusions:
            raise ValueError("Aucune observation Marché traçable pour la sortie UNRESOLVED.")
        return {
            "schema": "lawradar-agent-enrichment-v1",
            "agent": "market",
            "signal_id": observations.get("signal_id"),
            "status": "UNRESOLVED",
            "observed_at_utc": observed_at,
            "summary": "La qualification Marché n'a pas produit de réponse exploitable ; aucune conclusion de marché n'est tirée.",
            "sources": [],
            "limitations": [f"Réponse Claude non exploitable : {cause}"],
            "details": {
                "signal_hash": observations.get("signal_hash"),
                "collection_status": observations.get("collection_status"),
                "observations_total": len(observations.get("observations", [])),
                "conclusions": conclusions,
            },
            "score": None,
        }
    raise ValueError("Agent de qualification inconnu.")


def _looks_like_enrichment(value: Any, agent: str) -> bool:
    required = {
        "schema", "agent", "signal_id", "status", "observed_at_utc",
        "summary", "sources", "limitations", "details", "score",
    }
    return isinstance(value, dict) and value.get("agent") == agent and set(value) == required


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
    try:
        result = json.loads(_text(message))
    except (ValueError, json.JSONDecodeError) as error:
        return unresolved_enrichment(payload, agent, str(error))
    if not _looks_like_enrichment(result, agent):
        return unresolved_enrichment(payload, agent, "Le JSON Claude ne respecte pas le contrat d'enrichissement.")
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
