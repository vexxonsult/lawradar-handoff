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
    "evidence_status": "VERIFIED | PARTIAL | MISSING",
    "peripheral_service_evidence": [
      {
        "service_type": "PRESTATIONS_DE_SERVICES | LOGICIELS | CONSEIL | MISE_EN_RELATION | LOGISTIQUE",
        "source_kind": "OFFICIAL_TEXT | BOAMP",
        "source_url": "https://...",
        "excerpt": "extrait qui nomme explicitement le service B2B",
        "scope_excludes_regulated_acts": true,
        "scope_exclusion_excerpt": "extrait excluant explicitement vente, dispensation et distribution du médicament",
        "evidence_status": "VERIFIED"
      }
    ]
  }
}
```

- `OUT_OF_PROFILE` ne signifie pas que le secteur est interdit : il signifie
  que l'offre directe n'est pas compatible avec les compétences et
  autorisations actuelles du profil versionné.
- Un mot-clé isolé (`logiciel`, `conseil`, `logistique`, etc.) ne prouve pas un
  rôle légal. Il produit au mieux la route `SERVICE_SCOPE_CHECK_ONLY`.
- `peripheral_role_evidence` ne peut ouvrir `FULL_ENRICHMENT` que si une source
  officielle ou BOAMP traçable décrit un des services B2B autorisés **et**
  exclut explicitement vente, dispensation et distribution du médicament.
  L'autorisation d'un partenaire ne se transfère jamais au profil opérateur.
- `HOLD` route seulement vers `LEGAL_ROLE_CHECK_ONLY` : aucune recherche
  Presse, BOAMP, Demande, Marché ou décision Entrepreneur n'est lancée.
- Le filtre ne déclare jamais un rôle légal possible sur la seule base d'un
  changement réglementaire.
