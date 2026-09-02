# Porte d'accès opérateur — v1

Cette porte déterministe est évaluée avant les collectes Presse, Demande,
Marché et tout appel de l'agent Entrepreneur. Elle évite de dépenser des
requêtes sur une activité directe qui n'est pas accessible au profil opérateur.

Un fait d'opportunité peut porter l'objet optionnel suivant :

```json
{
  "operator_access": {
    "sector": "MEDICINES | FINANCIAL_SERVICES | LEGAL_SERVICES | OTHER_REGULATED | NOT_CLASSIFIED",
    "direct_offer_status": "ACCESSIBLE | OUT_OF_PROFILE | UNKNOWN | NOT_APPLICABLE",
    "peripheral_role_evidence": "VERIFIED | PARTIAL | MISSING | NOT_APPLICABLE",
    "evidence_status": "VERIFIED | PARTIAL | MISSING"
  }
}
```

- `OUT_OF_PROFILE` ne signifie pas que le secteur est interdit : il signifie
  que l'offre directe n'est pas compatible avec les compétences et
  autorisations actuelles du profil versionné.
- `peripheral_role_evidence` ne peut être `VERIFIED` que si une source établit
  un rôle légalement distinct de la vente, de la dispensation, du conseil
  réglementé ou de la prescription.
- `HOLD` route seulement vers `LEGAL_ROLE_CHECK_ONLY` : aucune recherche
  Presse, BOAMP, Demande, Marché ou décision Entrepreneur n'est lancée.
- Le filtre ne déclare jamais un rôle légal possible sur la seule base d'un
  changement réglementaire.
