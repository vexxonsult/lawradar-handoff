# Contrat commun des enrichissements — v1

Ce contrat prépare les agents **Presse**, **Demande** et **Marché**. Il ne les
active pas et ne leur donne aucun droit de modifier le Radar.

## Entrée autorisée

Un agent ne reçoit qu'un signal de `lawradar-universal-signal-v1`, son
identifiant stable et les liens de preuve déjà associés. Il ne consulte pas les
anciens signaux comme exemples ni comme sources de repli. La preuve primaire,
le changement détecté, le statut (`RETAINED`, `DISCARDED` ou `UNRESOLVED`) et
la raison du Radar sont immuables.

## Sortie minimale commune

Chaque résultat doit contenir :

```json
{
  "schema": "lawradar-agent-enrichment-v1",
  "agent": "press | demand | market",
  "signal_id": "signal:…",
  "status": "COMPLETED | NO_EVIDENCE | UNRESOLVED | FAILED",
  "observed_at_utc": "date ISO-8601",
  "summary": "constat concis et attribué",
  "sources": [
    {
      "url": "https://…",
      "title": "titre de la source",
      "published_at": "date si connue",
      "retrieved_at_utc": "date ISO-8601",
      "supports": "affirmation précise soutenue par cette source"
    }
  ],
  "limitations": ["ce qui manque ou ce qui reste incertain"],
  "score": null
}
```

`score` reste `null` tant qu'une méthode versionnée définit son échelle, ses
critères et sa provenance. L'absence de résultat est un résultat valable :
elle s'écrit `NO_EVIDENCE`, jamais comme une estimation.

## Rôle de chaque agent

| Agent | Question à laquelle il répond | Ce qu'il ne peut pas conclure |
| --- | --- | --- |
| Presse | Une couverture éditoriale indépendante existe-t-elle et que rapporte-t-elle ? | Que cette couverture prouve la réalité réglementaire ou la demande. |
| Demande | Quelles preuves mesurables d'intérêt ou de recherche existent-elles ? | Un volume, une tendance ou une intention d'achat sans source mesurable. |
| Marché | Quelles offres, acteurs et contraintes de marché sont documentés ? | Une taille de marché, un chiffre d'affaires ou un avantage concurrentiel sans preuve. |

## Garde-fous

- Aucun agent ne modifie `source`, `radar` ou `money_flows`.
- Toute affirmation importante renvoie vers une source précise et datée.
- Aucune recherche, publication, contact commercial, achat ou dépense n'est
  autorisé par ce contrat.
- L'agent Entrepreneur ne reçoit que les enrichissements terminés et sourcés ;
  il est traité dans une phase ultérieure.

## Conditions d'activation

Avant toute automatisation, il faut :

1. publier un premier dossier universel issu d'un vrai moteur réussi ;
2. choisir les sources autorisées et leurs conditions d'utilisation ;
3. fixer la fréquence, le plafond de coût et la règle d'arrêt ;
4. ajouter un schéma exécutable et des tests de non-altération du Radar.
