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

La collecte JORF effectue une pige matinale à 05:17, puis toutes les trente
minutes jusqu'à 08:17. Les horaires GitHub portent explicitement le fuseau
`Europe/Paris` : ils restent donc identiques lors des passages CET/CEST. Dès
que l'édition datée du jour est acquise, un verrou déterministe désactive les
tentatives suivantes et le succès du collecteur réveille immédiatement le
moteur.

Un Message Batch en cours est repris toutes les vingt minutes entre 05:09 et
16:49, sans nouvelle soumission. Les fenêtres de 17:17, 18:17 et 19:17 servent
à la consolidation BOAMP et au rattrapage. La fenêtre de 19:17 publie aussi
l'état du backlog. Chaque réveil passe d'abord par la file locale : zéro
candidat signifie zéro requête Anthropic.

## Sobriété du cycle

Après la collecte, le workflow publie `evidence/delta-latest.json`. Il compare mécaniquement la livraison du jour à la précédente, en ignorant les seuls horodatages techniques. `evidence_change_detected` indique toute variation collectée ; `model_input_required` indique uniquement une variation relevant du moteur actuel (JORF ou ConsultDD). Une variation EUR-Lex est donc visible sans déclencher Claude. Sans candidat pris en charge, le centre de contrôle enregistre explicitement un moteur `skipped` avec sa raison. En cas de changement documentaire pris en charge, les preuves brutes citées restent la seule source à interpréter.

Lorsqu'un appel modèle est requis, le moteur utilise l'API Message Batches :
toute la file quotidienne est soumise dans un lot unique jusqu'au plafond de
sûreté de 250 candidats, avec un contexte isolé et une sortie JSON par candidat,
et une facturation Batch à 50 % du tarif Messages standard. Le fichier
`evidence/motor-batch-latest.json` permet de reprendre un lot encore en cours
sans le soumettre une seconde fois. Le secret GitHub `ANTHROPIC_API_KEY` est
obligatoire ; le jeton `CLAUDE_CODE_OAUTH_TOKEN` ne donne pas accès à cette API.
Sans clé API, le centre de contrôle enregistre un run ignoré et aucun coût n'est
engagé.

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

Après une moisson Batch réussie, les branches Presse et BOAMP sont déclenchées
automatiquement pour chaque signal autorisé. La branche BOAMP produit les
sorties Demande et Marché à partir d'une collecte commune. Les artefacts des
branches convergent dans `out/client-context.json` ; le noyau versionné reste
inchangé. Le client Entrepreneur ne reçoit ce contexte qu'après convergence et
n'appelle Claude que si les filtres déterministes sont à `PASS`.
Un marqueur compact `evidence/client-orchestration-latest.json` empêche les
créneaux 18:17 et 19:17 de répéter une consolidation déjà réussie ; ils restent
disponibles comme reprises si le créneau précédent a échoué.

## Recyclage déterministe des opportunités bloquées

`scripts/utils/recycle_backlog.py` conserve séparément les signaux retenus dont
les faits versionnés donnent un filtre `HOLD`, `WATCH`, `INVESTIGATE` ou
`DISCARD`. Son registre durable, `evidence/recycle-backlog-latest.json`, garde
les faits source, les raisons de blocage et les empreintes de la politique et
du profil opérateur utilisés.

Lorsqu'une règle ou le profil change, le script rejoue les mêmes faits sans IA
ni réseau. Il produit un manifeste de réouverture uniquement si les filtres
retournent réellement `PASS` et si la porte opérateur autorise la collecte.
Une réouverture doit ensuite repasser par les enrichissements Presse, Demande
et Marché avant tout appel du client Entrepreneur. La file moteur, elle, ne
contenant que des empreintes, ne peut jamais à elle seule créer une fausse
opportunité à partir d'un texte sans contenu primaire.

## Axe Énergie / CEE

Les fiches d'opération standardisées CEE, bonifications officielles et mesures
d'efficacité énergétique à périmètre professionnel identifiable constituent un
axe de veille séparé. Elles sont conservées pour enquête B2B (presse, demande,
marché et partenaires), même lorsque le montant ou la faisabilité restent
inconnus. Cette route ne donne pas au projet le droit d'installer, certifier,
valoriser des CEE ou agir pour un obligé : elle borne l'activité à la veille,
la qualification et la mise en relation documentée.
