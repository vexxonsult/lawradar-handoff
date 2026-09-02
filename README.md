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

La collecte est lancée chaque jour à 17 h 20 Europe/Paris en heure d’été (`20 15 * * *` UTC). Le moteur Claude GitHub démarre à 17 h 35 ; il reste inactif lorsqu'aucun candidat pris en charge n'est présent dans le diff.

## Sobriété du cycle

Après la collecte, le workflow publie `evidence/delta-latest.json`. Il compare mécaniquement la livraison du jour à la précédente, en ignorant les seuls horodatages techniques. `evidence_change_detected` indique toute variation collectée ; `model_input_required` indique uniquement une variation relevant du moteur actuel (JORF ou ConsultDD). Une variation EUR-Lex est donc visible sans déclencher Claude. Sans candidat pris en charge, le centre de contrôle enregistre explicitement un moteur `skipped` avec sa raison. En cas de changement documentaire pris en charge, les preuves brutes citées restent la seule source à interpréter.

## Rendu de restitution

Le dépôt contient aussi un moteur GitHub Actions, filtré par le delta. Lorsqu'il
est requis, il produit une livraison structurée puis un dashboard déterministe.
Ces deux fichiers sont téléversés comme artefact du run GitHub Actions,
distinct du code public : ils ne sont ni committés dans ce dépôt, ni écrits
dans Google Drive. Leur accès reste régi par les paramètres GitHub du dépôt.

## Observabilité — phase 4

Chaque collecte publie aussi `evidence/run-manifest-latest.json`. Chaque exécution du moteur met à jour `evidence/run-manifest-motor-latest.json` puis joint son manifeste à l’artefact. `evidence/run-index-latest.json` rassemble les derniers statuts et le workflow de collecte joint un dashboard de contrôle HTML à son artefact. Ces données décrivent le run, ses fichiers d'entrée et de sortie, leurs empreintes et la durée mesurée, sans recopier les preuves ni inventer une consommation.

## Dossier universel de signal — phase 5

Lorsqu’un moteur aboutit, il publie `evidence/universal-signal-latest.json`. Ce dossier rassemble, sans nouvelle interprétation, les preuves compactes, la décision du Radar, les flux éventuellement démontrés et trois emplacements explicitement vides pour les futurs agents Presse, Demande et Marché. Ces agents ne pourront qu’ajouter une sortie sourcée dans leur emplacement ; ils ne modifieront ni la preuve ni la décision du Radar.
