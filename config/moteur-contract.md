# Contrat du moteur GitHub

Le moteur ne lit que les preuves versionnées dans ce dépôt. Son entrée commence
par `evidence/delta-latest.json` : si `model_input_required` est faux, il ne
doit pas être invoqué.

Quand il est invoqué, il ne fait aucune recherche web, aucun appel HTTP et ne
conclut jamais qu'une information est absente parce qu'une source est
inaccessible ou incomplète. Il distingue explicitement `UNRESOLVED` de
`DISCARDED`.

Il écrit exactement un fichier `out/motor-delivery.json`, conforme à
`config/moteur-delivery-schema.json`. Une valeur inconnue est écrite comme une
phrase explicite (par exemple « Non chiffré dans la preuve lue »), jamais
inventée. Un flux ne peut être créé que si le payeur, le bénéficiaire ou la
direction sont étayés par les preuves lues ; sinon le signal reste
`UNRESOLVED` dans `opportunities`.

Les résultats sont téléversés comme artefact GitHub Actions. Ils ne sont ni
committés dans ce dépôt public, ni écrits dans Google Drive.
