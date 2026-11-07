---
title: "Modèle de données"
subtitle: "Gestion intégrée du poste clients — version 1.0"
---

# 1. Principes

- **Une seule base relationnelle** (PostgreSQL) partagée par tous les modules.
- **Les soldes ne sont jamais saisis** : ils résultent des affectations. Les champs « réglé » et « solde » des factures et échéances sont des caches mis à jour dans la même transaction que l'affectation, et contrôlés en permanence contre le détail (contrôle de concordance).
- **Montants** : `NUMERIC(18,3)` ; cours de change : `NUMERIC(18,6)` (TND pour 1 unité de devise).
- **Aucune suppression physique** des opérations validées (déclencheurs de protection).
- Script complet de création : `database/schema.sql` (généré par Alembic, comprenant tables, contraintes et déclencheurs).

# 2. Tables et relations

```
customers 1──n invoices 1──n installments 1──n allocations n──1 payments
                   │  └──n invoice_lines                    ├─n──1 invoices (avoir)
                   │  └──n invoice_taxes                    └─n──1 adjustments
                   └──n provisions n──1 provision_campaigns
customers 1──n payments ; customers 1──n dunning_actions 1──n dunning_action_invoices n──1 invoices
customers 1──n risk_snapshots ; journal_entries 1──n journal_lines
approval_requests 1──n adjustments ; users 1──n user_sessions ; audit_log (autonome, chaîné)
```

| Table | Rôle | Clés et contraintes principales |
|---|---|---|
| `customers` | Fiche client : identité, matricule fiscal, contacts, banque, conditions, plafond, encours maximal, classification, risque (cache) | `code` unique ; statut ACTIF / BLOQUE / ARCHIVE |
| `invoices` | Factures **et** avoirs (`doc_type`) : totaux HT/TVA/autres/TTC, devise, cours, contre-valeur TND, réglé, solde, cycle de vie, classement | (`doc_type`, `number`) unique ; contraintes sur les valeurs ; déclencheur d'intangibilité |
| `invoice_lines` | Lignes : désignation, quantité, prix, remise, code et taux TVA figés | protégées après validation |
| `invoice_taxes` | Récapitulatif figé des taxes par taux (TVA, timbre, FODEC…) | protégées après validation |
| `installments` | Échéances : date, montant, contre-valeur TND, réglé | (`invoice_id`, `seq`) unique ; seul le « réglé » peut évoluer après validation |
| `payments` | Règlements : moyen, dates de réception / valeur / remise / encaissement / rejet / annulation, montant, devise, cours, affecté | `number` unique ; montant > 0 ; suppression interdite ; montants intangibles |
| `adjustments` | OD au crédit du client : écart de règlement, passage en perte, abandon de créance | intangibles |
| `allocations` | Lettrage : un crédit (règlement **ou** avoir **ou** OD) → une échéance ; montants devise / TND facture / TND source ; écart de change ; date d'effet ; contre-passation | une et une seule source (contrainte CHECK) ; suppression interdite ; contre-passation unique |
| `dunning_levels`, `dunning_templates` | Niveaux et modèles de relance | paramétrables |
| `dunning_actions`, `dunning_action_invoices` | Historique des actions de recouvrement et factures concernées (avec solde à la date de l'action) | |
| `risk_snapshots` | Historique des notations (score, classe, détail des critères) | |
| `provision_campaigns`, `provisions` | Campagnes et lignes de provision par facture (référentiel, base, taux suggéré/retenu, dotation/reprise, justification, déductibilité) | validation par une autre personne |
| `journal_entries`, `journal_lines` | Écritures proposées / validées / exportées | lignes ≥ 0 ; intangibles après export |
| `approval_requests` | Demandes soumises au principe des quatre yeux | |
| `parameters` | Moteur de paramétrage daté (clé, valeur JSON, date d'effet, source, « à valider ») | (`key`, `valid_from`) unique |
| `tax_rates`, `payment_methods`, `currencies`, `exchange_rates`, `reference_values`, `sequences` | Référentiels | |
| `users`, `user_sessions` | Utilisateurs, rôles, verrouillage, sessions révocables | |
| `audit_log` | Journal d'audit chaîné SHA-256 | UPDATE / DELETE interdits par déclencheur |
| `attachments` | Pièces justificatives (empreinte SHA-256, stockage disque) | |

# 3. Invariants vérifiés automatiquement

1. Σ montants des échéances = TTC de la facture ; Σ contre-valeurs TND = TTC TND.
2. Réglé d'une échéance = Σ affectations actives ; réglé de la facture = Σ réglés des échéances ; solde = TTC − réglé.
3. Affecté d'un règlement = Σ affectations actives ≤ montant ; un règlement rejeté ou annulé n'a plus d'affectation active.
4. Pour chaque client et à toute date : solde du grand livre auxiliaire = Σ restes dus TND − crédits non affectés TND (les écarts de change sont des mouvements du grand livre).
5. Toute écriture comptable est équilibrée.
6. La chaîne d'empreintes du journal d'audit est continue.

Ces contrôles sont exécutés par l'endpoint `/api/v1/coherence`, affichés sur le tableau de bord et dans *Intégration comptable*, lancés chaque nuit, et couverts par les tests automatisés.

# 4. Stratégie de migration

- Les évolutions de schéma sont versionnées par **Alembic** (`backend/migrations/versions`) ; elles sont appliquées automatiquement au démarrage du conteneur (`alembic upgrade head`).
- Toute migration est précédée d'une sauvegarde (procédure dans le guide d'installation).
- Reprise de l'existant : import Excel/CSV des clients puis des factures ouvertes (mode simulation obligatoire avant import réel).
