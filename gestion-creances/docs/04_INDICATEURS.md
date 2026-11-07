---
title: "Indicateurs et conventions de calcul"
subtitle: "Gestion intégrée du poste clients — version 1.0"
---

Toutes les formules ci-dessous sont implémentées dans `backend/app/services/kpi.py`, `ledger.py` et `risk.py`, restituées dans l'interface (icône d'information) et couvertes par des tests automatisés. Montants en TND, au cours historique de chaque pièce.

# 1. Encours

| Indicateur | Définition |
|---|---|
| Total des créances (brut) | Σ restes dus des échéances des factures validées à la date d'arrêté |
| Non échues / échues | Restes dus dont l'échéance est postérieure / antérieure à la date d'arrêté |
| Douteuses, litigieuses | Restes dus des factures ainsi classées |
| Crédits non affectés | Règlements non lettrés (avances), avoirs non imputés, OD non affectées |
| Créances nettes | Brut − crédits non affectés (= solde du grand livre auxiliaire) |
| Encours de risque client | Créances ouvertes + chèques et effets reçus non encore encaissés |

# 2. Balance âgée

Tranches (paramètre `aging.buckets`) : non échu ; 1–30 ; 31–60 ; 61–90 ; 91–180 ; plus de 180 jours. L'ancienneté est le nombre de jours entre la date d'échéance **de chaque échéance** et la date d'arrêté (une facture payable en trois fois peut apparaître dans trois tranches). Le reste dû à la date d'arrêté est recalculé à partir des affectations datées : la balance âgée d'une date passée est exacte.

# 3. DSO (délai moyen de recouvrement)

- **Méthode comptable** (par défaut) : DSO = créances TTC brutes à la date / CA TTC des N derniers jours × N, avec N = 90 (paramètre `dso.period_days`). CA TTC = factures − avoirs validés de la période.
- **Méthode par épuisement** (*count-back*) : on retranche de l'encours les ventes TTC des mois précédents, du plus récent au plus ancien ; le DSO est le nombre de jours de ventes nécessaires pour couvrir l'encours. Plus fidèle lorsque l'activité est saisonnière.

Exemple testé : encours 1 191 TND, CA 90 jours 2 382 TND → DSO comptable = 45 jours.

# 4. Taux de recouvrement

Taux = encaissements de la période / montants exigibles × 100, où exigible = restes dus échus à l'ouverture de la période + échéances tombant dans la période. Période par défaut : 30 jours glissants.

*Limite connue* : les encaissements de la période peuvent inclure des avances, ce qui peut porter le taux au-delà de 100 %.

# 5. Taux d'impayés

Taux = créances échues impayées / total des créances brutes à la date × 100.

# 6. Concentration du risque

- Part des N premiers débiteurs (N = 5 par défaut) dans le total des créances.
- Indice de Herfindahl-Hirschman : HHI = Σ (part de chaque client)² × 10 000. Au-delà de 2 500 : forte concentration ; 10 000 = un seul client.

# 7. Notation de risque (score 0 à 100)

| Critère (pondération par défaut) | Points |
|---|---|
| Part échue de l'encours (20) | 20 × part échue |
| Ancienneté du plus vieil impayé (20) | 20 × min(jours / 180 ; 1) |
| Retard moyen pondéré des règlements sur 12 mois (15) | 15 × min(retard / 90 ; 1) |
| Fréquence des paiements en retard (10) | 10 × part des règlements payés au-delà de 5 jours de tolérance |
| Incidents de paiement sur 12 mois (15) | 15 × min(rejets / 3 ; 1) |
| Utilisation du plafond (10) | 0 jusqu'à 80 %, maximum à 120 % ; sans plafond défini : 50 % des points |
| Poids dans le portefeuille (5) | 5 × min(part / 25 % ; 1) |
| Dégradation récente (5) | 5 × min(hausse du retard moyen 3 derniers mois / 30 jours ; 1) |

Classes : faible < 25 ≤ modéré < 50 ≤ élevé < 75 ≤ critique (paramètre `risk.thresholds`). Règle de prudence : un client en contentieux ou ayant des créances douteuses ou litigieuses est au minimum en risque élevé. Chaque recalcul est historisé ; une dégradation de classe déclenche une alerte.

# 8. Prévision d'encaissement

Date probable = échéance + retard médian historique du client (24 mois, au moins 3 règlements) ; à défaut, médiane de tous les clients ; à défaut, échéance contractuelle. Si la date calculée est passée : aujourd'hui + 7 jours. Les chèques et effets en portefeuille sont pris à leur date de valeur. Exclusions : créances douteuses, litigieuses ou de plus de 180 jours.
