# Phase 3 — livrables de simulation

Ce dossier décrit les essais reproductibles de la Phase 3. Il ne contient ni
registre de production, ni journal de production, ni dashboard.

## Scénarios validés le 30 août 2026

1. **Cycle isolé sur les sources officielles.** Le collecteur DILA, EUR-Lex,
   ConsultDD, le paquet brut et le delta ont été exécutés dans un répertoire
   temporaire distinct de `evidence/`.
2. **Journée stable.** Deux copies identiques des preuves produisent
   `model_input_required: false` et aucune source à relire.
3. **Changement de métadonnées.** Une nouvelle borne de couverture JORF sans
   document nouveau produit `METADATA_CHANGED`, pas une lecture IA.
4. **Changement documentaire.** Une variation des cartes ConsultDD produit
   `CHANGED` : la veille doit relire uniquement cette source.
5. **Rendu du dashboard hors modèle.** `scripts/render_dashboard.py` valide
   un résultat compact du moteur (`lawradar-dashboard-input-v1`) et produit le
   HTML. L'IA ne doit donc plus générer ni transporter le HTML complet.

## Commande de contrôle

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

Pour essayer le rendu sans aucune donnée de production :

```sh
python3 scripts/render_dashboard.py --input simulation/phase-3/dashboard-input-example.json --out /tmp/lawradar-dashboard.html
```

## Critère de sécurité

`METADATA_CHANGED` ne ferme aucune dette et ne constitue jamais une preuve
d'absence. Le modèle ne peut ignorer une source que lorsque le delta indique
explicitement qu'aucun document n'a changé.
