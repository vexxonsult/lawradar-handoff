# État Phase 3 — moteur GitHub validé

Date de contrôle : 31 août 2026.

## Chaîne GitHub validée

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
- le canal Claude Code ↔ GitHub est validé avec le jeton OAuth de
  l'abonnement Claude ;
- le moteur prépare d'abord un diff compact des preuves : Claude ne lit ni le
  corpus JORF complet ni Google Drive ;
- le moteur produit `motor-delivery.json`, le valide, puis rend le dashboard
  de façon déterministe ;
- les trois fichiers du run (`motor-input.json`, `motor-delivery.json`,
  `dashboard.html`) sont publiés comme artefact GitHub Actions, jamais comme
  commit dans le dépôt public ;
- le run de validation complet 33400296127 a réussi en 47 secondes ;
- 22 tests automatiques passent.

## Résultats de la simulation isolée

Le cycle complet a été exécuté hors de `evidence/` et hors de Drive. Il a
confirmé qu’une mise à jour JORF de simple couverture est
`METADATA_CHANGED`, que EUR-Lex était inchangé, et que les cartes ConsultDD
étaient réellement modifiées : seule cette dernière source doit être relue.

## Limites explicitement conservées

Le nouveau trajet GitHub ne dépend plus de Drive. Le précédent moteur Claude
qui écrit sur Drive doit néanmoins être désactivé ou mis en pause dans son
espace Claude, afin d'éviter toute double exécution : ce dépôt ne peut pas
arrêter une planification externe.

Le contrat GitHub est volontairement prudent : un candidat sans preuve locale
suffisante devient `UNRESOLVED` et aucun flux n'est inventé. Le registre métier
historique des dettes et la future lecture multi-agents relèvent de la phase 4,
pas de cette migration 3C.
