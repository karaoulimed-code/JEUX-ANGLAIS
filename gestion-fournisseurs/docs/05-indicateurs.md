# Indicateurs : formules, périmètres et conventions

Toutes les valeurs sont en **TND**, converties au **cours historique** de chaque facture. Les pièces prises en compte sont les factures, factures d'acompte et avoirs **validés** (une facture annulée sort du calcul à sa date d'annulation). Date d'arrêté = date du jour sauf choix contraire.

| Indicateur | Formule | Périmètre / convention |
|---|---|---|
| Solde d'une facture | TTC − Σ affectations de règlements émis ou débités − Σ imputations d'avoirs/acomptes | À une date : seules les opérations datées ≤ date d'arrêté |
| Total des dettes fournisseurs | Σ soldes positifs des factures et acomptes | Avoirs et avances non imputés présentés à part (solde net) |
| Dettes échues | Σ soldes dont l'échéance < date d'arrêté | — |
| Dettes non échues | Total − échues | — |
| Dettes en litige | Σ min(solde, montant contesté) des factures ayant un litige ouvert ou en cours | — |
| Balance âgée | Retard = date d'arrêté − échéance ; tranches : non échu (≤ 0), 1-30, 31-60, 61-90, 91-180, > 180 jours | Par fournisseur, devise, catégorie |
| Achats de la période | Σ TTC des factures de la période − Σ TTC des avoirs de la période | Période glissante (365 jours par défaut) |
| **DPO** | Total des dettes à la date d'arrêté ÷ achats TTC de la période × nombre de jours de la période | Méthode « dettes de fin de période » ; TTC au numérateur et au dénominateur pour la cohérence |
| Délai moyen de paiement | Σ (montant affecté × (date de paiement − date de facture)) ÷ Σ montants affectés | Paiements de la période, pondéré par les montants |
| Taux de paiement à échéance | Σ montants payés au plus tard à l'échéance ÷ Σ montants payés | Paiements de la période |
| Taux de factures litigieuses | Nombre de factures de la période ayant eu un litige ÷ nombre de factures de la période | — |
| Engagements non facturés | Σ (quantité commandée − quantité facturée) × prix × (1 + TVA) | Commandes approuvées, partiellement ou totalement reçues, non clôturées |
| Concentration top 5 | Σ dettes des 5 premiers créanciers ÷ total des dettes | — |
| Indice HHI | Σ (part de chaque fournisseur en %)² | 10 000 = un seul fournisseur ; > 2 500 = forte concentration |
| Évolution mensuelle | Total des dettes au dernier jour de chacun des 12 derniers mois | Recalcul historique (approximation : les rejets de chèques sont pris à leur date de rejet) |
| Prévisions | **Certain** : soldes non contestés des factures validées nets de retenue + moyens de paiement émis non débités ; **Probable** : factures en validation, commandes non facturées (livraison prévue + délai de paiement), contrats récurrents ; **Conditionnel** : montants en litige | Retards positionnés à la date du jour ; horizons 7, 30, 60, 90, 365 jours et profil mensuel 12 mois |
| Trésorerie disponible | Σ (solde d'ouverture + lignes de relevé) − paiements émis non débités | Par compte de trésorerie |
| Escompte : rendement annualisé | t ÷ (1 − t) × 365 ÷ (jours gagnés) | Recommandé si supérieur au coût de financement paramétré (10 % par défaut) |
| Score de risque fournisseur (0–100) | Dépendance (≥ seuil : 25 pts ; ≥ moitié : 10) + litiges (5 à 20) + incidents (5/incident, max 15) + retards de livraison (5/retard, max 15) + évaluation < 3/5 + risque de rupture ≥ 4 (10) + criticité (10) + classement « à risque » (15) | Niveaux : modéré ≥ 30, élevé ≥ 55, critique ≥ 75 (paramétrables) |
