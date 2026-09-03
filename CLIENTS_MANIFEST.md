# Manifeste des clients externes LawRadar

Le noyau (« Mine d'Or ») produit un unique export neutre :
`out/universal-signal.json`, conforme à `lawradar-universal-signal-v2`.
Il contient les preuves compactes, décisions Radar, faits d'opportunité et
emplacements d'enrichissement. Il ne contient aucune conclusion commerciale
d'un client.

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

Dans l'orchestration automatique, Presse et la branche BOAMP
(Demande/Marché) écrivent des artefacts isolés. Le script
`scripts/consolidate_client_artifacts.py` les assemble dans
`out/client-context.json`, copie de travail extérieure au noyau. Cette copie
porte les filtres déterministes nécessaires au client Entrepreneur ; le fichier
`evidence/universal-signal-latest.json` reste immuable pendant le fan-out.
Seul un marqueur technique sans conclusion métier,
`evidence/client-orchestration-latest.json`, est versionné pour rendre les
reprises de 18:17 et 19:17 idempotentes.

## Client initial

`scripts/clients/entrepreneur_agent.py` prépare une livraison
`lawradar-client-entrepreneur-delivery-v1`. Il vérifie la présence des filtres
et de la porte opérateur dans le snapshot V2 ; il écrit `SKIPPED`, avec zéro
appel externe, dès que le signal n'est pas à `PASS` ou que la porte opérateur
n'autorise pas la collecte externe. Son entrée ne peut jamais être sa propre
sortie.

L'évaluation Claude est opt-in : `--run-claude` requiert `ANTHROPIC_API_KEY`
dans l'environnement d'exécution et le SDK Python officiel `anthropic`. Elle
est réalisée avec un unique appel borné au modèle configuré (Sonnet 4.6 par
défaut), sans outil, sans recherche web et sans écriture dans le noyau. La
sortie est contrôlée : URLs déjà présentes dans le signal, commission de 5 à
10 % seulement sur une assiette chiffrée source, et premier pas réversible de
sept jours maximum.

## Extensions prévues

Des consommateurs indépendants peuvent être ajoutés sans modifier le noyau :

- `scripts/clients/linkedin_journalist_agent.py` ;
- `scripts/clients/video_scriptwriter_agent.py` ;
- `scripts/clients/b2b_alert_sales_agent.py`.

Ils doivent respecter exactement les cinq règles ci-dessus. Aucun client ne
devient une dépendance du collecteur, du moteur ou du schéma universel.
