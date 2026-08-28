# LawRadar FR

Infrastructure de secours du Radar réglementaire.

Le Radar conserve son raisonnement dans Claude. Ce dépôt ne produit **aucune
interprétation réglementaire ou économique** : il récupère les archives
officielles DILA, vérifie leur intégrité et fabrique des preuves brutes que la
veille peut citer.

## Règle de conservation

- les archives `.tar.gz` DILA sont temporaires et ne sont jamais ajoutées au
  dépôt ;
- le dépôt conserve un manifeste vérifiable (URL, date, taille, SHA-256) ;
- seuls les textes explicitement suivis sont conservés en JSON, avec leur XML
  source et une transcription mécanique ;
- le dossier `evidence/latest/` est l'inbox destiné à la veille ;
- aucune clé, aucun secret, aucune donnée personnelle, aucun dashboard ou
  registre de production ne doit être commité ici.

## Utilisation locale

```sh
python3 scripts/collect_dila_jorf.py --targets config/jorf_targets.json --out evidence/latest
```

La commande choisit la dernière archive JORF publiée par DILA, contrôle son
format et écrit un manifeste. Elle échoue proprement si aucune archive valide
ne peut être lue. Elle ne remplace jamais une preuve déjà publiée sans laisser
le manifeste du passage courant.

Le workflow GitHub Actions l'exécute chaque soir : c'est un collecteur léger,
pas un agent d'analyse.
