# Manifeste des clients externes LawRadar

Le noyau (« Mine d'Or ») produit un unique export neutre :
`out/universal-signal.json`, conforme à `lawradar-universal-signal-v2`.
Il contient les preuves compactes, décisions Radar, faits d'opportunité et
enrichissements sourcés Presse, Demande et Marché. Il ne contient aucune
conclusion commerciale d'un client.

## Règle Hub & Spoke

`scripts/clients/` est la seule zone des consommateurs métier externes.
Chaque client :

1. lit `out/universal-signal.json` en lecture seule ;
2. ne modifie ni preuve, ni statut Radar, ni enrichissement du noyau ;
3. écrit une livraison indépendante nommée
   `out/client-<nom>-delivery.json` ;
4. possède son propre prompt, ses propres limites et ses propres tests ;
5. ne déclenche aucune publication, prise de contact, dépense ou action
   irréversible sans une autorisation distincte.

## Client initial

`scripts/clients/entrepreneur_agent.py` prépare uniquement une livraison
`lawradar-client-entrepreneur-delivery-v1`. Il vérifie la présence des filtres
et de la porte opérateur dans le snapshot V2 ; il ne produit aucune décision
business tant que ces préconditions ne sont pas démontrées. Son entrée ne peut
jamais être sa propre sortie.

## Extensions prévues

Des consommateurs indépendants peuvent être ajoutés sans modifier le noyau :

- `scripts/clients/linkedin_journalist_agent.py` ;
- `scripts/clients/video_scriptwriter_agent.py` ;
- `scripts/clients/b2b_alert_sales_agent.py`.

Ils doivent respecter exactement les cinq règles ci-dessus. Aucun client ne
devient une dépendance du collecteur, du moteur ou du schéma universel.
