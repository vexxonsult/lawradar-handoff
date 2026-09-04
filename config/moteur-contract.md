# Contrat du moteur GitHub

Le moteur ne lit que les preuves versionnées dans ce dépôt. Il construit d'abord
un diff compact de JORF et ConsultDD : s'il ne contient aucun candidat, le
modèle ne doit pas être invoqué, même si une autre source collectée a changé.

EUR-Lex est collecté et versionné comme preuve officielle, mais son
interprétation n'est pas encore dans le périmètre du moteur de Phase 3. Il sera
branché sur son agent réglementaire dédié, plutôt que de provoquer aujourd'hui
des appels modèle sans candidat exploitable.

Quand il est invoqué, le moteur soumet au maximum 250 requêtes indépendantes à
l'API Message Batches d'Anthropic. Chaque requête ne reçoit qu'un candidat et
n'a accès à aucun outil, aucune recherche web, aucun autre fichier et aucune
mémoire historique. La seule sortie du modèle est un objet JSON contraint par
schéma. Le code assemble ensuite les objets, rattache chaque réponse à son
`source_id` et valide la livraison complète. Il distingue explicitement
`UNRESOLVED` de `DISCARDED`.

L'intégration utilise l'interface stable du SDK officiel
`client.messages.batches`, et non l'ancienne interface bêta. Elle requiert le
secret GitHub `ANTHROPIC_API_KEY`, distinct du jeton d'abonnement Claude Code.
En son absence, le run est enregistré comme ignoré, sans appel fournisseur et
sans faire avancer la file.

Un batch asynchrone peut survivre à un run GitHub. Son identifiant, l'empreinte
du lot, le modèle et les compteurs techniques sont conservés dans
`evidence/motor-batch-latest.json`, avec l'entrée candidate figée qui garantit
la jointure lors de la moisson, mais sans recopier les réponses du fournisseur.
Le run suivant reprend cet identifiant : il ne resoumet jamais le même lot tant
que le batch existe. La file n'avance que lorsque toutes les réponses du lot
borné (250 au maximum) sont
terminées, présentes, correctement rattachées et validées. Une réponse absente,
expirée, annulée ou en erreur bloque donc tout le lot sans perte de candidat.

Le dossier `evidence/universal-signal-latest.json` est le **pointeur courant**
V2 destiné aux agents du noyau et aux clients externes. Chaque lot complet est
d'abord scellé dans l'archive append-only
`evidence/universal-signals/v2/AAAA/MM/run-<id>-attempt-<n>.json` (avec un
manifeste immuable adjacent) ; il n'est jamais une
entrée du moteur. Le moteur ne
doit ni le lire, ni le prendre comme exemple, ni réutiliser ses acteurs,
montants, liens ou raisonnements. À chaque run, toute conclusion doit provenir
exclusivement des candidats présents dans `out/motor-input-resolved.json`, le
snapshot figé réellement soumis ou repris par le batch. Un run sans candidat
envoyé au modèle scelle tout de même son audit compact des préfiltres en mode
archive seule ; il ne déplace pas le pointeur `latest` des clients.

Le code d'assemblage écrit exactement un fichier `out/motor-delivery.json`, conforme à
`config/moteur-delivery-schema.json`. Chaque décision contient une fiche
`lawradar-opportunity-facts-v1` associée exactement à son `source_id`. Cette
fiche n'est pas une idée commerciale : elle porte les termes de recherche et
les faits juridiques ou opérationnels directement établis ; capital, délai,
autorisation et rôle opérateur non prouvés restent respectivement `null`,
`UNKNOWN` ou `MISSING`. Une valeur inconnue est écrite comme une
phrase explicite (par exemple « Non chiffré dans la preuve lue »), jamais
inventée. Un flux ne peut être créé que si le payeur, le bénéficiaire ou la
direction sont étayés par les preuves lues ; sinon le signal reste
`UNRESOLVED` dans `opportunities`.

Dans le dossier universel, une lecture réellement présente porte la provenance
neutre `MOTOR_STRUCTURED_READING`. Ce libellé atteste l'assemblage et la
validation par le contrat du Moteur ; il ne prétend pas prouver quel fournisseur
ou modèle a généré le contenu. Les seules lectures artificielles des scénarios
de crash-test portent `SIMULATOR` et sont refusées par le profil d'archive de
production. Le schéma V2 générique continue d'accepter les anciens flux sans
champs de liaison, mais l'archive durable exige `source_id`, `signal_id` et
`link_status` pour chaque nouveau flux.

Les résultats sont téléversés comme artefact GitHub Actions. Ils ne sont ni
committés dans ce dépôt public, ni écrits dans Google Drive.

Le tarif Batch annoncé par Anthropic réduit de 50 % le coût des tokens par
rapport aux appels Messages synchrones. Cette réduction ne dispense pas de la
limite de 250 candidats, du filtre delta-first ni de la mesure des tokens
réellement retournés par chaque réponse.

Les consommateurs métier (Entrepreneur, journaliste, vidéo, alertes B2B) sont
hors du moteur. Ils vivent dans `scripts/clients/`, lisent uniquement
`out/universal-signal.json` et écrivent une livraison indépendante ; le
manifeste `CLIENTS_MANIFEST.md` fixe cette frontière.
