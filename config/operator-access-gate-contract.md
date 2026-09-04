# Porte d'accès opérateur — v1

Cette porte déterministe est évaluée avant les collectes Presse, Demande,
Marché et tout appel de l'agent Entrepreneur. Elle évite de dépenser des
requêtes sur une activité directe qui n'est pas accessible au profil opérateur.

Un fait d'opportunité peut porter l'objet optionnel suivant :

```json
{
  "operator_access": {
    "sector": "MEDICINES | FINANCIAL_SERVICES | LEGAL_SERVICES | ENERGY_EFFICIENCY | OTHER_REGULATED | NOT_CLASSIFIED",
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

## Axe Énergie / efficacité énergétique

`ENERGY_EFFICIENCY` couvre notamment une fiche d'opération standardisée CEE ou
une bonification officielle qui crée un périmètre professionnel identifiable.
Quand l'offre directe est explicitement limitée à la veille B2B, à la
qualification du besoin et à la recherche de partenaires (`ACCESSIBLE` ou
`NOT_APPLICABLE`), la porte autorise les collectes Presse, Demande et Marché.
Cette ouverture ne vaut **ni** autorisation d'installer un équipement, **ni**
capacité à monter ou valoriser un dossier CEE, **ni** mandat d'un obligé : ces
prestations exigent toujours des preuves et partenaires propres au signal.

## Données de contact et médicaments

Une liste de collectivités, d'établissements ou de contacts ne constitue jamais
une preuve de demande, de rôle B2B légal ou d'autorisation de prospecter. Elle
ne doit pas être fournie au Radar, aux agents ni à Claude. Pour un médicament,
la porte conserve `HOLD` tant qu'une source officielle ou BOAMP ne démontre pas
un service périphérique précis et exclut explicitement vente, dispensation,
distribution et promotion du médicament.
