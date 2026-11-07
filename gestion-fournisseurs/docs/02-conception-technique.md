# Conception technique

## 1. Choix technologiques

| Option évaluée | Verdict | Motif |
|---|---|---|
| **Python + FastAPI** (backend) | Retenu | Arithmétique décimale exacte (`Decimal`) indispensable aux millimes ; écosystème d'exports (openpyxl, reportlab) ; voie naturelle pour l'IA ; API documentée automatiquement (OpenAPI) |
| **PostgreSQL** | Retenu | Transactions ACID, `NUMERIC` exact, verrouillage de ligne pour la numérotation, sauvegarde `pg_dump` standard |
| **React + TypeScript** (frontend, Vite) | Retenu | Interface riche type ERP, typage, construction en fichiers statiques servis par l'API (un seul service à déployer) |
| Next.js | Écarté | Rendu serveur inutile pour une application métier authentifiée ; ajoute un second serveur Node |
| Tout TypeScript (Node) | Écarté | Absence de type décimal natif : risque d'erreurs d'arrondi sur les montants |

## 2. Architecture

```
┌──────────────── Navigateur (React, FR/AR/EN) ────────────────┐
│ Tableau de bord · Fournisseurs · Achats · Factures · …        │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTPS / JSON (jeton Bearer)
┌──────────────────────────────▼───────────────────────────────┐
│ FastAPI — couche API (app/api/*) : validation, droits          │
│        ↓                                                      │
│ Services métier (app/services/*) — règles centralisées :       │
│  suppliers · purchasing · invoices (contrôles) · payments ·    │
│  accounting · analytics (KPI, prévisions, risques) · exports   │
│        ↓                    ↘ common : audit chaîné, numérot., │
│ Modèle SQLAlchemy (app/models.py)   paramètres, taux, devises  │
└──────────────────────────────┬───────────────────────────────┘
                               │
                 PostgreSQL 16 + stockage des pièces (disque)
```

Principes :
- **Règles métier centralisées** dans `app/services` ; l'API ne fait que valider les entrées, vérifier les droits et appeler les services. Les tests portent directement sur les services et sur l'API.
- **Aucune règle fiscale codée en dur** : taux datés (`tax_rates`), comptes (`account_mappings`), seuils et tolérances (`settings`).
- **Intégration du cycle** : chaque service met à jour les objets liés dans la même transaction (ex. validation de facture → quantités facturées du BC + écriture comptable + journal d'audit).
- **Irréversibilité** : pas de suppression de pièce validée ; annulation et contre-passation.

## 3. Organisation du code

```
backend/
  app/config.py        variables d'environnement (AP_*)
  app/models.py        33 tables
  app/permissions.py   profils et matrice des droits
  app/security.py      mots de passe PBKDF2, JWT révocables, inactivité
  app/services/        règles métier (un fichier par domaine)
  app/api/             routes REST (104 opérations)
  app/ai/              interfaces IA (extraction, assistant) et score de prix
  app/seed.py          paramètres fiscaux et données de démonstration
  migrations/          Alembic (scripts de migration)
  tests/               54 tests automatisés
  manage.py            migrate · init-company · demo · verify-audit
frontend/src/          pages React, composants, i18n, formats tunisiens
scripts/               sauvegarde.sh · restauration.sh
docker-compose.yml     PostgreSQL + application
```

## 4. Base de données

Schéma détaillé et diagramme des relations : `03-schema-base-de-donnees.md` (généré depuis le code).

Tables principales : `suppliers`, `supplier_bank_accounts`, `supplier_contracts`, `purchase_requests(_lines)`, `purchase_orders(_lines)`, `goods_receipts(_lines)`, `invoices`, `invoice_lines`, `invoice_approvals`, `credit_allocations`, `payments`, `payment_allocations`, `payment_runs`, `treasury_accounts`, `bank_statement_lines`, `disputes`, `journal_entries`, `journal_lines`, `tax_rates`, `account_mappings`, `settings`, `exchange_rates`, `audit_logs`, `users`, `user_sessions`.

Choix de modélisation clés :
- Le **solde d'une facture** n'est pas stocké : il est recalculé (TTC − affectations de paiements émis − imputations d'avoirs/acomptes), ce qui garantit la cohérence factures / règlements et permet la balance âgée à **n'importe quelle date passée**.
- Les **affectations** (`payment_allocations`) sont exprimées en TTC devise facture, avec la part de retenue et l'écart de change.
- `company_id` sur chaque table métier : cloisonnement multi-entreprises.

## 5. API

Référence complète : `09-reference-api.md` ; documentation interactive : `/api/docs`. Conventions : JSON, dates ISO `AAAA-MM-JJ`, montants décimaux, erreurs métier `422 {detail, code}`, droit insuffisant `403`, conflit (doublon) `409`.

## 6. Sécurité

| Exigence | Mise en œuvre |
|---|---|
| Authentification | Mot de passe PBKDF2-SHA256 (390 000 itérations, sel aléatoire) ; politique 10 caractères lettres + chiffres |
| Sessions | JWT signé contenant un identifiant de session stocké en base : révocation à la déconnexion, expiration (8 h), fermeture après 30 min d'inactivité |
| Force brute | Verrouillage 15 min après 5 échecs ; échecs journalisés |
| Droits | 25 permissions × 8 profils, vérifiés côté serveur sur chaque route |
| Séparation des tâches | Contrôlée dans les services (demandeur ≠ valideur ≠ réceptionnaire ≠ contrôleur ; préparateur ≠ autorisateur ≠ exécutant ; saisisseur de RIB ≠ vérificateur) ; paramètre `separation_stricte` pour les très petites structures (assouplissement tracé) |
| Traçabilité | `audit_logs` : qui, quand, IP, action, avant/après ; chaînage SHA-256 (chaque ligne contient l'empreinte de la précédente) ; contrôle d'intégrité par l'écran Audit ou `manage.py verify-audit` |
| Données | Isolation par entreprise ; pièces jointes limitées en type et taille, empreinte SHA-256 ; en-têtes de sécurité HTTP |
| Transport | HTTPS via reverse proxy (Nginx/Caddy) — voir guide d'installation |
| Sauvegardes | `pg_dump` + archive des pièces + empreintes, rotation 30 jours, restauration testée |

## 7. Intelligence artificielle (module 12)

Architecture par interfaces (`app/ai`) : chaque fonction est aujourd'hui assurée par des règles **explicables**, remplaçables par un modèle sans toucher au reste.

| Fonction | État |
|---|---|
| Doublons de factures / fournisseurs | Actif (normalisation, similarité, montant/date) |
| Variations anormales de prix | Actif (écart à la moyenne historique ; score z disponible) |
| Priorités de paiement | Actif (score + justification écrite par facture) |
| Risque et dépendance fournisseurs | Actif (score 0–100 avec facteurs) |
| Prévision des besoins de trésorerie | Actif (déterministe : certain / probable / conditionnel) |
| Lecture automatique des factures | Point d'extension `InvoiceExtractor` — renvoie 501 « non activé » |
| Analyse de contrats, rédaction de rapports | Point d'extension `TextAssistant` |

Règle intangible : aucune sortie de l'IA ne déclenche une opération sensible ; elle produit un brouillon ou une proposition validé par un utilisateur habilité.

## 8. Évolution SaaS multi-entreprises

| Exigence | Préparation actuelle | Reste à faire |
|---|---|---|
| Séparation stricte des données | `company_id` partout, filtrage systématique | Ajouter la sécurité au niveau ligne PostgreSQL (RLS) en défense en profondeur |
| Configuration comptable par entreprise | Taux, comptes, seuils par entreprise | — |
| Gestion autonome des utilisateurs | Administrateur par entreprise | Invitation par e-mail, double authentification |
| Abonnements, console centrale | — | Module d'abonnement et super-administration |
| Plusieurs pays / référentiels | Paramétrage des taxes et comptes | Jeux de paramètres par pays, traductions complètes |

## 9. Maquettes (captures de l'application réelle)

Les écrans livrés sont fonctionnels ; quelques captures (données de démonstration) :

- `captures/tableau-de-bord.png` — indicateurs, ancienneté, prévisions, alertes
- `captures/facture-controles.png` — facture avec anomalies bloquantes du rapprochement
- `captures/optimisation-paiements.png` — préparation des paiements avec justifications
- `captures/balance-agee.png` — balance âgée à date
- `captures/fiche-fournisseur.png` — fiche fournisseur

## 10. Plan de tests

54 tests automatisés (`pytest`), exécutés sur SQLite et sur PostgreSQL :

| Thème exigé | Tests |
|---|---|
| Enregistrement des factures | totaux, timbre, RS, échéance net / fin de mois, statuts |
| Rapprochement à trois niveaux | conforme, quantité non reçue, cumul, prix dans / hors tolérance, sans BC, dépassement |
| Avoirs / acomptes / avances | imputation d'avoir, facture d'acompte (écriture 401/409/TVA), avance puis imputation |
| Retenue à la source / TVA | seuil 1 000 DT, honoraires sans seuil, prorata et reliquat exact, taux non en vigueur, non-assujetti |
| Règlements partiels, affectation, groupés | paiement partiel, double paiement empêché, paiement groupé, campagne |
| Balance âgée | tranches, date d'arrêté passée, paiement postérieur, avoirs et avances |
| DPO, délai, ponctualité | formules vérifiées sur cas chiffré |
| Prévisions | certain / probable / conditionnel par horizon ; priorités et escompte |
| Devises | écart de change réalisé et écriture équilibrée |
| Rapprochement comptable | écritures équilibrées, 404/43661 pour immobilisations, auxiliaire = général, balance auxiliaire |
| Droits et séparation des tâches | 403 par profil, saisisseur / réceptionnaire / préparateur / autorisateur, RIB, seuils DG |
| Traçabilité | actions journalisées, détection d'altération du journal |
| Sécurité | verrouillage après échecs, déconnexion, session invalide |
| Exports et import | 13 états × 3 formats, import CSV avec erreurs ligne à ligne |

Lancer : `cd backend && pytest` (SQLite) ou `AP_TEST_DATABASE_URL=postgresql+psycopg://… pytest`.
