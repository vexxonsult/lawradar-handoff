# LawRadar — canal public de preuves primaires

Ce dépôt est un canal de transfert mécanique vers la couche de surveillance du Radar.

Il contient uniquement :

- un collecteur des archives officielles DILA JORF ;
- la liste explicite des identifiants recherchés ;
- les tests du collecteur ;
- le dernier paquet de preuves primaires brutes.

Aucune interprétation réglementaire ou économique n’est produite ici. Les champs `interpretation` restent à `null`. Les journaux complets, prompts, registres, dashboards et données privées ne sont pas publiés. Le paquet primaire est construit et publié par GitHub Actions : Google Drive ne fait pas partie de ce trajet de collecte.

## Fichier stable pour la surveillance

`https://raw.githubusercontent.com/vexxonsult/lawradar-handoff/main/evidence/primary-evidence-latest.json`

Schéma attendu : `lawradar-primary-handoff-v1`.

## Planification

La collecte est lancée chaque jour à 17 h 20 Europe/Paris en heure d’été (`20 15 * * *` UTC), avant la veille Claude de 17 h 45.

## Sobriété du cycle

Après la collecte, le workflow publie `evidence/delta-latest.json`. Il compare mécaniquement la livraison du jour à la précédente, en ignorant les seuls horodatages techniques. Une variation de couverture sans document nouveau est marquée `METADATA_CHANGED` : elle ne déclenche pas de relecture IA. La veille lit ce delta en premier ; si `model_input_required` vaut `false`, aucun long corpus ne doit être relu. En cas de changement documentaire, les preuves brutes citées restent la seule source à interpréter.

## Rendu de restitution

Le dépôt contient aussi `scripts/render_dashboard.py`. Il prend un résultat
moteur strictement structuré et construit le HTML sans interpréter, rechercher
ou reformuler les preuves. Le dépôt public ne contient aucun résultat de
production ni dashboard : seul le code de rendu y est publié.
