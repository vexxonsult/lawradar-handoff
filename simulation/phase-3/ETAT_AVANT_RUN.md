# État Phase 3 avant le prochain run officiel

Date de contrôle : 31 août 2026.

## Prêt pour demain

- le collecteur officiel s’exécute depuis GitHub Actions et n’utilise plus
  Google Drive ;
- le paquet primaire, les sommaires JORF, EUR-Lex, ConsultDD et le delta sont
  versionnés sur GitHub ;
- le delta distingue `UNCHANGED`, `METADATA_CHANGED`, `CHANGED`, `NEW`,
  `MISSING` et `ABSENT` ;
- une journée stable ne demande aucune relecture de corpus ;
- une source dont la couverture avance sans document nouveau ne réveille pas le
  modèle ;
- une variation documentaire réelle reste transmise à la veille ;
- la veille est passée sur Sonnet 5 et lit le delta avant les corpus ;
- le projet Claude de veille est rattaché au dépôt public
  `vexxonsult/lawradar-handoff` ;
- le dashboard peut être rendu de façon déterministe à partir d'un résultat
  moteur court et validé : le modèle n'a plus à générer le HTML ;
- le canal Claude Code ↔ GitHub a été validé depuis GitHub Actions avec le
  jeton OAuth de l'abonnement Claude : lecture du delta réussie en 28 secondes,
  sans écriture ;
- 18 tests automatiques passent.

## Résultats de la simulation isolée

Le cycle complet a été exécuté hors de `evidence/` et hors de Drive. Il a
confirmé qu’une mise à jour JORF de simple couverture est
`METADATA_CHANGED`, que EUR-Lex était inchangé, et que les cartes ConsultDD
étaient réellement modifiées : seule cette dernière source doit être relue.

## Frontière restante, volontairement non masquée

Le moteur Money Flow publié dans la tâche Claude continue aujourd’hui à écrire
son registre, ses flux et son dashboard sur Drive. Le collecteur et la veille
ne dépendent plus de Drive pour leurs preuves ; le moteur, oui, pour ses
livrables. Le canal d’authentification et de lecture GitHub est maintenant en
place. Le passage complet à GitHub exige encore de migrer le contrat métier
complet du moteur vers une sortie structurée, puis de décider du dépôt de
publication des livrables : ce dépôt est public et ne doit pas recevoir de
registre ni de données privées par défaut.

Cette frontière ne doit pas être déclarée résolue avant une simulation distincte
du moteur : journal non-production → sortie structurée → rendu HTML
déterministe → empreintes et reprise. Le renderer, son contrat et le canal
GitHub sont désormais présents et testés ; il manque le contrat métier complet
et l'émetteur automatique du résultat structuré vers un espace de restitution
approprié. Elle ne bloque pas la collecte ni la veille sobre de demain, mais
empêche de déclarer la Phase 3 entièrement close.
