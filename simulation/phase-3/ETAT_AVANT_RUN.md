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
livrables. Le passage complet à GitHub exige un canal d’écriture automatique du
moteur vers GitHub ou un exécuteur de code qui applique ses sorties structurées.

Cette frontière ne doit pas être déclarée résolue avant une simulation distincte
du moteur : journal non-production → sortie structurée → rendu HTML
déterministe → empreintes et reprise. Le renderer et son contrat sont désormais
présents et testés ; il manque uniquement l'émetteur automatique du résultat
structuré vers GitHub. Elle ne bloque pas la collecte ni la veille sobre de
demain, mais empêche de déclarer la Phase 3 entièrement close.
