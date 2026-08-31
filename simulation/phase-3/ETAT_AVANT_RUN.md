# État Phase 3 — clôturée et validée

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
- le modèle n'est appelé que si ce diff contient au moins un candidat JORF ou
  ConsultDD effectivement pris en charge ; un changement EUR-Lex seul ne
  consomme donc plus de crédits inutilement ;
- le moteur produit `motor-delivery.json`, le valide, puis rend le dashboard
  de façon déterministe ;
- les trois fichiers du run (`motor-input.json`, `motor-delivery.json`,
  `dashboard.html`) sont publiés comme artefact GitHub Actions, jamais comme
  commit dans le dépôt public ;
- la collecte finale 33408913849 a réussi ;
- le moteur final 33409291402 a réussi en 1 min 11 s et son artefact a été lu
  et contrôlé, pas seulement son statut GitHub ;
- 25 tests automatiques passent.

## Résultat fonctionnel final

Sur les trois consultations réellement candidates lors de ce contrôle, deux
ont été `DISCARDED` faute de preuve financière locale. La consultation du
permis de carrières de Larchant a été `RETAINED` sur une unique preuve
officielle : l'acte de cautionnement solidaire n°513.2599, dans le dossier
CAMINO joint à la consultation. Il établit ING Bank N.V. comme caution de
Sibelco France au bénéfice du préfet de Seine-et-Marne, dans la limite de
2 103 543 €.

Il s'agit d'une garantie conditionnelle, appelable seulement en cas de
défaillance de Sibelco : le moteur ne la présente donc jamais comme un paiement
déjà intervenu. Le différend de redevance de fortage, non chiffré par les
extraits officiels, reste explicitement hors des flux publiés.

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
suffisante devient `UNRESOLVED` et aucun flux n'est inventé. EUR-Lex est
collecté comme preuve officielle, mais son interprétation sera raccordée à son
agent réglementaire dédié en phase 4. Le registre métier historique des dettes
et la future lecture multi-agents relèvent aussi de la phase 4, pas de cette
migration 3C.
