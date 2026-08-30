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

## Commande de contrôle

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Critère de sécurité

`METADATA_CHANGED` ne ferme aucune dette et ne constitue jamais une preuve
d'absence. Le modèle ne peut ignorer une source que lorsque le delta indique
explicitement qu'aucun document n'a changé.
