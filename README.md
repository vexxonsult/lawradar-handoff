# LawRadar — canal public de preuves primaires

Ce dépôt est un canal de transfert mécanique vers la couche de surveillance du Radar.

Il contient uniquement :

- un collecteur des archives officielles DILA JORF ;
- la liste explicite des identifiants recherchés ;
- les tests du collecteur ;
- le dernier paquet de preuves primaires brutes.

Aucune interprétation réglementaire ou économique n’est produite ici. Les champs `interpretation` restent à `null`. Les journaux complets, prompts, registres, dashboards et données privées ne sont pas publiés.

## Fichier stable pour la surveillance

`https://raw.githubusercontent.com/vexxonsult/lawradar-handoff/main/evidence/primary-evidence-latest.json`

Schéma attendu : `lawradar-primary-handoff-v1`.

## Planification

La collecte est lancée chaque jour à 17 h 20 Europe/Paris en heure d’été (`20 15 * * *` UTC), avant la veille Claude de 17 h 45.
