# Contrat de l’agent Marché — V0

L’agent Marché répond à une question circonscrite : **quelles offres, quels
acteurs ou quelles contraintes de marché sont documentés autour du signal
courant ?**

Il ne reçoit qu’un signal `RETAINED` et un fichier
`lawradar-market-observations-v1` préparé pour ce signal. Il n’explore pas le
web librement, ne lit aucun ancien signal ni l’historique d’un acteur, et ne
modifie jamais le Radar, ses preuves, les flux financiers ou les résultats des
autres agents.

## Sources prévues, mais désactivées en V0

- registres publics d’entreprises, après choix du territoire et de la licence ;
- marchés publics, après définition du vocabulaire sectoriel et de la fenêtre ;
- sites d’offres, seulement après vérification de leurs conditions d’usage ;
- sources d’études de marché sous licence, jamais par contournement de paywall.

La V0 ne lance aucune recherche, ne crée aucune clé API, ne contacte aucun
acteur et ne dépense rien. Une observation future doit contenir l’URL ou la
référence, l’acteur observé, le type d’observation, la zone, la date de
récupération et un extrait de preuve de 25 mots au maximum.

## Format de sortie

La sortie commune utilise `lawradar-agent-enrichment-v1` avec
`agent: "market"`, `score: null` et les `details` exacts suivants :

```json
{
  "signal_hash": "sha256 du signal reçu",
  "collection_status": "COMPLETED | NO_EVIDENCE | UNRESOLVED",
  "observations_total": 0,
  "conclusions": [
    {
      "url": "URL présente dans les observations",
      "interpretation": "OFFER | ACTOR | CONSTRAINT | NOT_RELEVANT | AMBIGUOUS",
      "why": "constat limité à la preuve observée"
    }
  ]
}
```

Règles :

- l’existence d’une offre ou d’un acteur ne prouve ni une taille de marché, ni
  un chiffre d’affaires, ni une concurrence exhaustive ;
- toute source ou conclusion doit provenir des observations du signal courant ;
- `COMPLETED` exige au moins une observation pertinente et une synthèse citée ;
- `NO_EVIDENCE` signifie que la collecte documentée n’a rien trouvé, jamais
  qu’il n’existe aucun marché ;
- une erreur, une source partielle ou une relation ambiguë vaut `UNRESOLVED` ;
- aucun score ni recommandation commerciale n’est calculé à ce stade.
