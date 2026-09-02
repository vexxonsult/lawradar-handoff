# Contrat de l’agent Entrepreneur — V0

L’agent Entrepreneur ne cherche aucune information. Il reçoit uniquement un
`lawradar-entrepreneur-input-v1` construit depuis **un signal courant** : sa
preuve compacte, la décision du Radar, les flux démontrés et les résultats
Presse, Demande et Marché déjà attachés à ce même signal.

Il ne consulte jamais un ancien dossier comme exemple. Il ne modifie ni le
Radar, ni les preuves, ni les enrichissements amont. Il ne publie rien, ne
contacte personne, n’engage aucune dépense et ne lance aucun test.

## Sortie

La sortie commune utilise `lawradar-agent-enrichment-v1` avec
`agent: "entrepreneur"`, `score: null` et les `details` exacts suivants :

```json
{
  "signal_hash": "sha256 du signal reçu",
  "support_statuses": {"press": "…", "demand": "…", "market": "…"},
  "decision": "WATCH | INVESTIGATE | TEST | DISCARD",
  "gaps": ["preuve ou mesure qui manque"],
  "test_protocol": null
}
```

Un `test_protocol` non nul est purement descriptif et contient uniquement
`hypothesis`, `method`, `success_signal`, `stop_condition` et
`max_duration_days` (1 à 30). Il ne porte ni budget, ni commande, ni instruction
d’exécution.

## Règles de décision

- si Presse, Demande ou Marché est `PENDING`, `UNRESOLVED` ou `FAILED`, la
  sortie est `UNRESOLVED`, la décision est `INVESTIGATE` et les manques sont
  explicités ;
- `WATCH` conserve une piste prouvée sans test immédiat ;
- `DISCARD` signifie « ne pas poursuivre avec les preuves actuelles », pas que
  le sujet est impossible ;
- `TEST` exige les trois agents amont terminés, au moins une preuve Demande ou
  Marché positive, des sources citées et un protocole réversible ;
- chaque source citée doit venir de la preuve compacte, d’un flux démontré ou
  d’un enrichissement amont fourni ;
- l’agent ne prédit jamais un revenu, un coût ou une probabilité de succès.
