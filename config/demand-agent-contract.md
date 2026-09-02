# Contrat de l’agent Demande — V0

L’agent Demande répond à une seule question : **quelles observations mesurées
montrent un intérêt, une recherche ou une intention autour du signal courant ?**

Il ne reçoit qu’un signal `RETAINED` et un fichier
`lawradar-demand-observations-v2` construit pour ce signal. Il ne lit aucun
ancien signal, ne fait pas de recherche web libre, n’accède pas aux historiques
de Presse et ne modifie jamais le Radar, ses preuves ou les flux financiers.

## Source active en V0 : demande publique BOAMP

Le pilote Marché interroge déjà BOAMP dans ses limites strictes. L'agent
Demande réutilise exactement ces avis, sans appel HTTP ou IA supplémentaire,
mais uniquement lorsqu'il s'agit d'un appel d'offres encore actif avec un lien
et un objet traçables. Il conclut seulement à une **intention d'achat public
formalisée**. Ce n'est ni une mesure de demande générale, ni une estimation de
marché, ni une intention d'achat privée.

## Sources prévues, mais désactivées

- Google Trends : indicateur d’intérêt relatif, non volume de recherche ;
- Google Ads Keyword Planner : volume estimé, soumis à un compte et à ses
  conditions d’usage ;
- Search Console : requêtes réellement reçues par un futur site LawRadar ;
- données de sondage ou de place de marché, seulement si la méthode, la période
  et la provenance sont documentées.

La V0 n’automatise aucune de ces sources additionnelles, ne crée aucune clé API
et ne dépense rien au-delà de la collecte BOAMP déjà autorisée. Une observation
peut être ajoutée plus tard seulement si elle porte une
URL ou une référence vérifiable, une date de récupération, une période, une
zone géographique, une métrique et son unité.

## Format de sortie

La sortie commune utilise `lawradar-agent-enrichment-v1` avec
`agent: "demand"`, `score: null` et les `details` exacts suivants :

```json
{
  "signal_hash": "sha256 du signal reçu",
  "collection_status": "COMPLETED | UNRESOLVED | SKIPPED_BY_OPERATOR_GATE",
  "indicators": {
    "trends": {"status": "DISABLED", "ratio_7d_vs_prior_83d": null, "surge_detected": null},
    "autocomplete": {"status": "DISABLED", "intent_terms_found": [], "commercial_intent": null},
    "institutional": {"status": "NONE | INSTITUTIONAL_DEMAND_OBSERVED | HIGH_INSTITUTIONAL_DEMAND"}
  },
  "observations_total": 0,
  "conclusions": [
    {
      "url": "URL présente dans les observations",
      "interpretation": "ATTENTION | SEARCH_INTEREST | COMMERCIAL_INTENT | NOT_RELEVANT | AMBIGUOUS",
      "why": "constat limité à la métrique mesurée"
    }
  ]
}
```

Règles :

- aucune source ou conclusion ne peut être ajoutée si elle n’est pas dans les
  observations reçues ;
- `COMPLETED` exige au moins une observation pertinente et une synthèse citée
  (`[1]`, `[2]`, …) ;
- `NO_EVIDENCE` signifie que la collecte documentée a abouti sans observation,
  jamais « il n’existe aucune demande » ;
- une erreur, une métrique ambiguë ou une couverture incomplète vaut
  `UNRESOLVED` ;
- l’agent ne transforme jamais un indice relatif en volume, ni un intérêt en
  intention d’achat ;
- aucun score n’est calculé avant une méthode versionnée.
