# Plan directeur — mise à jour v1.1, révisée le 2 septembre 2026

Ce document met à jour le **Plan directeur définitif — Radar d’opportunités** approuvé le 30 août 2026. Les phases 1 à 4 sont achevées. La base technique de la phase 5 est en place ; sa validation en conditions réelles attend le prochain moteur réellement appelé. Les principes, critères de validation et la structure à deux projets restent inchangés, avec les précisions ci-dessous comme référence opérationnelle.

## Projet A — ordre des phases confirmé

1. Fiabiliser le Radar officiel.
2. Valider le moteur Money Flow.
3. Stabiliser l’infrastructure et l’exploitation technique.
4. Construire l’observabilité et le centre de contrôle.
5. Créer le dossier universel de signal.
6. Brancher les agents Presse, Demande et Marché.
7. Construire le moteur de synthèse.
8. Ajouter l’agent Entrepreneur.

Le Radar est terminé à la validation de la phase 8. Le Projet B demeure l’exploitation de cet écosystème : expérimentations entrepreneuriales, production éditoriale, activités commerciales et amélioration continue.

---

## Phase 3 — Stabiliser l’infrastructure et l’exploitation technique

### Objectif

Rendre le Radar durable, reproductible, économe et facile à maintenir, sans abaisser le niveau de preuve, de traçabilité ou de reprise après incident.

GitHub est l'unique base opérationnelle : collecteurs, configurations, schémas, tests, preuves structurées, journaux techniques, versions et artefacts de dashboard. Google Drive ne fait partie d'aucun trajet actif ; il peut être supprimé ou conservé comme archive personnelle, sans incidence sur le Radar.

Le collecteur GitHub Actions tourne à 17 h 20 (heure d'été française). Le moteur Claude, lancé à 17 h 35, ne lit que le diff local préparé depuis les preuves GitHub et ne s'exécute que si ce diff contient un candidat pris en charge. Il ne consulte ni n'écrit Google Drive. Les livrables (`motor-input.json`, `motor-delivery.json`, dashboard) restent des artefacts GitHub Actions, distincts du dépôt public.

L'ancienne tâche Claude qui écrivait sur Drive n'est plus une composante du système. Elle doit rester en pause ou être supprimée dans l'espace Claude afin d'éviter tout doublon ; aucune nouvelle tâche Drive ne doit être créée pour le Radar.

Chaque cycle doit produire un manifeste indiquant son identifiant, les versions utilisées, les fichiers d’entrée et de sortie, les empreintes, les durées, le coût estimé, les statuts, les erreurs et les reprises éventuelles. Le système doit reprendre après interruption, empêcher les doubles écritures, conserver la dernière version valide et distinguer échec, couverture partielle et absence légitime de signal.

### Phase 3A — Audit de consommation et architecture des modèles

Cette sous-phase est obligatoire. Son audit initial peut commencer dès maintenant en lecture seule ; les changements de modèles, de prompts ou d’horaires ne seront appliqués qu’après validation du fonctionnement réel du cycle en cours.

#### Objectif

Réduire le coût quotidien sans réduire la fiabilité, la couverture, l’explicabilité ni la capacité de reprise.

#### Audit demandé

Pour chaque tâche planifiée et chaque composant, documenter :

- son objectif ;
- sa fréquence ;
- le modèle utilisé ;
- la longueur de son prompt ;
- les fichiers réellement lus et écrits ;
- les outils utilisés ;
- la durée observée ;
- le niveau de coût estimé ;
- les opérations répétées ou inutiles ;
- les opérations pouvant être faites par du code ;
- les opérations pouvant passer sur un modèle plus léger ;
- les opérations qui justifient un modèle puissant ;
- les dépendances empêchant une exécution sobre.

L’audit produit ensuite un budget cible journalier et mensuel, des seuils d’alerte, ainsi que des règles d’arrêt ou de dégradation contrôlée en cas de dépassement.

#### Architecture cible

| Type de travail | Exécutant par défaut |
| --- | --- |
| Collecte officielle, téléchargement, empreintes, comparaison, tests, archivage, validation de schéma | Code / GitHub Actions, sans IA |
| Tri simple, formatage, contrôles de structure, jour sans signal | Modèle léger |
| Interprétation réglementaire ou Money Flow standard | Modèle moyen |
| Signal ambigu, correction complexe, arbitrage à fort enjeu | Modèle puissant |
| Décision commerciale, dépense ou action externe | Intervention humaine explicite |

#### Règles de sobriété

- Fonctionnement **delta-first** : ne transmettre et ne traiter que les nouveautés, les corrections et les dettes réellement ouvertes.
- Réutilisation des résultats stables et cache des données déjà vérifiées.
- Données structurées plutôt que relecture quotidienne de longs journaux en prose.
- Prompts quotidiens courts ; invariants et contrôles transférés vers schémas, tests et configurations versionnés lorsque cela ne réduit pas la sûreté.
- Sorties structurées et concises ; pas de narration longue lorsque le format de sortie suffit.
- Arrêt immédiat des branches dont les conditions d’entrée ne sont pas remplies.
- Modèle puissant réservé aux cas apportant une interprétation réellement nécessaire.
- Mesure de la durée et de la consommation par composant à chaque cycle.

#### Validation de la phase 3 — acquise le 31 août 2026

La phase 3 n’est validée que si :

- le fonctionnement est indépendant du Drive ;
- la restauration et la reprise sont testées ;
- le classement et l’archivage sont automatiques ;
- coûts et durées sont visibles ;
- les fichiers ne sont pas dupliqués inutilement ;
- une documentation permet de comprendre le système ;
- chaque tâche est affectée au niveau d’exécution le moins coûteux compatible avec sa fiabilité ;
- les journées sans nouveauté ont un coût faible ;
- un coût élevé n’est engagé que pour un signal complexe ou important ;
- le budget cible et les seuils d’alerte sont définis.

Validation réalisée : les collectes et le moteur GitHub ont été exécutés et leurs artefacts contrôlés. Le moteur a retenu une garantie financière officielle de Larchant sans transformer une garantie conditionnelle en paiement effectif. Les changements sans candidat exploitable n'appellent plus Claude.

Le raccordement de l'interprétation EUR-Lex et des agents Presse, Demande et Marché reste volontairement hors de la phase 3.

## Phase 4 — Observabilité et centre de contrôle

### Objectif

Rendre chaque exécution lisible et vérifiable sans ajouter une nouvelle couche d'interprétation. Le centre de contrôle doit répondre à trois questions : quel run a eu lieu, quelles données ont été utilisées, et quel résultat a été produit ?

### Livrable 4A — Manifeste commun d'exécution

Le premier incrément de la phase 4 est en place : `scripts/build_run_manifest.py` produit un manifeste JSON versionné selon `lawradar-run-manifest-v1`.

Chaque manifeste enregistre :

- l'identifiant, la tentative, le workflow, le commit et l'URL du run ;
- le type de run (`collector` ou `motor`) et son statut ;
- les fichiers d'entrée et de sortie, leur présence, leur taille et leur empreinte SHA-256 ;
- la durée mesurée lorsqu'elle est disponible ;
- les reprises et erreurs déclarées ;
- l'état de coût fourni par le prestataire, sans inventer un nombre de tokens ou un montant.

Le collecteur publie `evidence/run-manifest-latest.json`. Le moteur joint `out/run-manifest.json` à son artefact, avec `motor-delivery.json` et le dashboard. Les manifestes ne contiennent pas le contenu des preuves : ils en assurent la traçabilité.

### Critères d'acceptation de 4A

- un test automatisé vérifie le schéma minimal, les empreintes et l'absence de contenu sensible ;
- les deux workflows produisent leur manifeste au terme d'un run réussi ;
- une exécution interrompue reste distinguable d'une absence légitime de signal ;
- la mesure de coût indique explicitement quand le fournisseur ne transmet pas la consommation détaillée.

### Suite de la phase 4

Le livrable 4B est un index de runs et un tableau de contrôle léger (statuts, durées, entrées/sorties, état de coût et liens d'artefacts), alimenté par ces manifestes. Il ne modifie ni les preuves primaires ni le contrat du moteur.

Un moteur non appelé est lui aussi un résultat : le centre de contrôle doit le versionner avec le statut `skipped`, sa raison et un coût `not_called`. La collecte générale distingue désormais une variation constatée d'une variation traitable par le moteur courant, afin qu'un changement EUR-Lex hors périmètre ne ressemble pas à un appel IA manqué.

### Validation de la phase 4 — acquise le 2 septembre 2026

Le centre de contrôle enregistre désormais les exécutions du collecteur comme du moteur, y compris un moteur volontairement non appelé. Une variation EUR-Lex apparaît comme une variation de preuve, avec la raison lisible « hors périmètre du moteur actuel », et non comme un appel IA manqué. Le statut, les entrées, sorties, empreintes et l'absence d'appel au modèle sont vérifiables dans les manifestes et l'index de runs.

## Phase 5 — Dossier universel de signal

### Objectif

Créer une fiche canonique et déterministe pour chaque sortie du Radar. Elle sépare strictement ce qui est prouvé, ce que le moteur a conclu, et ce que les futurs agents devront encore vérifier.

### Contrat

`lawradar-universal-signal-v1` contient :

- le lien vers le run, le commit et le périmètre de couverture ;
- un signal par candidat, avec sa preuve compacte, son changement et la décision du Radar ;
- les flux financiers seulement lorsqu'ils existent dans la livraison validée du moteur ;
- trois emplacements `PENDING` pour Presse, Demande et Marché ;
- les limites de couverture et le nombre de signaux non résolus.

Le dossier est construit par code après un moteur réussi, puis versionné sous `evidence/universal-signal-latest.json`. Les agents futurs n'auront pas le droit de modifier les preuves, le statut ou la raison du Radar : ils ne compléteront que leur propre emplacement avec des sources.

### Validation de la phase 5

- chaque opportunité du moteur est reliée à un candidat et à une seule preuve compacte ;
- le dossier refuse une décision orpheline ou dupliquée ;
- un dossier sans flux conserve explicitement `money_flows: []` ;
- les emplacements des agents restent vides et ne déclenchent aucun appel IA tant que la phase 6 n'est pas commencée.

### Validation de la phase 5 — acquise le 2 septembre 2026

Le contrat, le générateur, les tests et le raccordement au workflow moteur sont publiés. Un premier `universal-signal-latest.json` a été construit à partir de l'artefact immuable d'un moteur réellement réussi (run `33409291402`, Larchant/Sibelco), sans nouvel appel IA ni faux signal. Il relie un signal retenu à sa décision Radar, à sa preuve compacte et à son flux conditionnel démontré ; les trois emplacements d'enrichissement restent `PENDING`. Les prochains moteurs réellement appelés produiront le même dossier automatiquement.

## Phase 6 — Contrats des agents Presse, Demande et Marché

### Objectif

Préparer trois enrichissements indépendants du Radar, chacun limité à son rôle et incapable de modifier une preuve officielle ou une décision du moteur. Cette préparation ne déclenche ni recherche externe ni appel IA.

### Règles de branchement

- un agent reçoit un signal universel identifié et les liens de preuve déjà associés ;
- il produit une sortie sourcée, datée, concise et séparée de la décision Radar ;
- il peut conclure `NO_EVIDENCE` ou `UNRESOLVED`, sans inventer de score ni de volume ;
- il n'écrit que son emplacement (`press`, `demand` ou `market`) ;
- une décision commerciale, une dépense ou une publication reste interdite à ce stade ;
- les agents ne seront activés qu'après la première validation réelle de la phase 5 et après choix explicite des sources, du budget et de la fréquence.

Le contrat de sortie commun est versionné dans `config/agent-enrichment-contract-v1.md`. Il constitue le prochain livrable préparatoire ; l'activation des agents est une étape distincte et contrôlée.

### Livrable 6A — porte d'entrée protégée

Le schéma `config/agent-enrichment-schema.json` et le script
`scripts/merge_agent_enrichment.py` permettent d'ajouter une sortie d'agent à
un seul emplacement vide. Ils refusent un signal inconnu, l'écrasement d'une
sortie existante et tout score tant qu'une méthode n'a pas été définie. Des
tests vérifient que la preuve primaire, la décision Radar et les flux restent
strictement inchangés.

### Livrable 6B — collecte Presse déterministe

Le collecteur `scripts/collect_press_candidates.py` prépare des requêtes à
partir du seul signal `RETAINED` courant. Il interroge GDELT (source d'appoint)
et trois flux RSS complémentaires : Localtis / Banque des Territoires (édition
institutionnelle), Actu-Environnement (presse spécialisée) et The Conversation
France (analyse académique sous Creative Commons). Il conserve titres, médias,
dates et extraits RSS limités à 25 mots, puis déduplique les candidats. Il ne
lit pas le corps des articles, ne consulte aucun signal historique et ne fait
aucun appel IA. Google News RSS complète ces flux comme couche de découverte
large, limitée aux titres et liens issus de requêtes construites depuis le
signal courant ; il n'est jamais une preuve autonome. Pour éviter qu'un mot
générique n'entraîne un appel IA, deux termes distinctifs sont exigés, sauf si
le signal n'en contient qu'un seul. Une panne de l'une de ces sources est
tracée mais ne masque pas une collecte réussie par une autre ; sans source
réussie, le statut reste `UNRESOLVED`.

### Livrable 6C — qualification Presse contrôlée

Le contrat `config/press-qualification-contract.md` et le contrôleur
`scripts/validate_press_enrichment.py` imposent que toute synthèse Presse ne
citer que des candidats réellement collectés. Ils refusent une URL inventée,
un `NO_EVIDENCE` après une erreur de collecte, une synthèse sans renvoi vers
ses sources et une sortie non liée au signal courant. Aucun modèle n'est encore
appelé : le prochain incrément sera son branchement contrôlé derrière ce
contrôleur.

### Livrable 6D — pilote Presse manuel

Le workflow `agent-presse-lawradar.yml` ne possède aucune planification : il
ne peut être lancé qu'à la demande, pour un identifiant de signal `RETAINED`.
Il appelle GDELT pour ce seul signal, puis n'appelle Sonnet qu'en présence de
candidats et sans erreur de collecte ; le plafond est d'un appel par run. Sans
candidat, il écrit `NO_EVIDENCE` sans IA ; en cas de panne, il écrit
`UNRESOLVED`. Une seule reprise est possible après `UNRESOLVED`, avec
conservation de la première tentative ; toute sortie finale est validée avant
d'être fusionnée dans le seul emplacement Presse du dossier universel.

### Livrable 6E — redondance de collecte Presse

La V0 ajoute les flux RSS de Localtis / Banque des Territoires,
Actu-Environnement et The Conversation France en complément de GDELT. Les
collectes restent déterministes : aucun corps d'article n'est téléchargé, et un
item RSS n'est proposé que s'il partage au moins deux termes distinctifs avec
le signal courant. Le résultat reste `NO_EVIDENCE` dès qu'au moins une source
répond mais ne fournit aucun candidat lié ; chaque panne reste visible dans les
artefacts. Le type de source est conservé afin de ne jamais présenter une
couverture institutionnelle ou académique comme une couverture de presse
indépendante.

### Livrable 6F — contrat Demande sans dépense

L’agent Demande est préparé sans collecte automatique : son contrat exige des
observations mesurées, datées et géolocalisées, et interdit de convertir un
indice d’intérêt en volume de recherche ou en intention d’achat. Google Trends,
Keyword Planner et Search Console restent explicitement désactivés, donc aucun
compte, crédit, clé API ou appel IA n’est créé. Un contrôleur valide que chaque
conclusion et chaque source viennent strictement des observations du signal
courant avant toute fusion dans son emplacement `demand`.

### Livrable 6G — contrat Marché sans prospection

L’agent Marché est préparé sans exploration web ni collecte automatique. Son
contrat exige que toute observation documente l’acteur, le type d’offre ou de
contrainte, la zone, la provenance et un extrait limité à 25 mots. Il interdit
de déduire une taille de marché, un chiffre d’affaires ou une concurrence
exhaustive à partir d’une simple offre observée. Les registres, marchés publics
et sites d’acteurs restent désactivés : aucun compte, contact, clé API, achat
ou appel IA n’est créé avant une décision de source et de périmètre.

### Livrable 6H — agent Entrepreneur, décision sans exécution

L’agent Entrepreneur reçoit exclusivement le signal courant, les flux déjà
prouvés et les résultats des trois agents amont. Il n’effectue aucune recherche
et ne peut produire qu’une décision documentée : `WATCH`, `INVESTIGATE`, `TEST`
ou `DISCARD`. Un agent amont manquant impose `UNRESOLVED` et `INVESTIGATE`.
Une décision `TEST` exige les trois apports terminés, une preuve Demande ou
Marché positive, des sources citées et un protocole réversible limité à 30
jours ; elle n’autorise ni dépense, ni publication, ni prise de contact.

---

## Rappel de la frontière entre les deux projets

**Projet A — Construction :** sources → preuves → Money Flow → enrichissements → synthèse → agent Entrepreneur → protocole de test. À cette étape, le Radar est terminé.

**Projet B — Exploitation :** tests entrepreneuriaux, média, contenu, produits et services. Les résultats observés servent à améliorer le Radar, mais ne sont pas nécessaires pour déclarer sa construction achevée.
