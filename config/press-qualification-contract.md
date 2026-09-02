# Contrat de qualification — agent Presse V0

L'agent Presse reçoit exclusivement un `lawradar-press-candidates-v1` et le
signal correspondant. Il ne fait aucune recherche, aucun appel HTTP et ne lit
aucun ancien signal universel.

Il retourne un `lawradar-agent-enrichment-v1` avec `agent: "press"`. La
structure spécifique de `details` est :

```json
{
  "signal_hash": "sha256 du signal reçu",
  "window": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"},
  "queries": [{"source": "gdelt-doc-2.0", "query": "…", "hits": 0}],
  "candidates_total": 0,
  "candidates_after_dedup": 0,
  "coverage_level": "NONE | LOW | MEDIUM | HIGH",
  "decisions": [
    {"url": "URL présente dans les candidats", "relevance": "DIRECT | CONTEXTUAL | NOT_LINKED | AMBIGUOUS", "why_linked": "justification courte"}
  ]
}
```

Règles impératives :

- une URL dans `sources` ou `decisions` doit figurer dans les candidats reçus ;
- `COMPLETED` exige au moins une source qualifiée `DIRECT` ou `CONTEXTUAL` ;
- `NO_EVIDENCE` exige zéro source retenue et zéro erreur de collecte ;
- si une collecte a échoué ou si la liaison reste ambiguë, le statut est
  `UNRESOLVED`, pas `NO_EVIDENCE` ;
- `FAILED` est réservé à une incohérence de structure ou de signal ;
- la synthèse ne peut citer que des éléments figurant dans les titres ou les
  extraits fournis, avec des renvois `[1]`, `[2]`, etc. vers `sources`.

Le contrôleur `scripts/validate_press_enrichment.py` applique ces règles avant
toute écriture dans le dossier universel.
