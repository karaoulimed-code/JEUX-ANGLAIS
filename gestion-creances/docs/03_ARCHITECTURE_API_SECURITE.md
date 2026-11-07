---
title: "Architecture, API et sécurité"
subtitle: "Gestion intégrée du poste clients — version 1.0"
---

# 1. Choix technologiques

| Couche | Choix | Justification |
|---|---|---|
| Base de données | PostgreSQL 16 | Transactions ACID, `NUMERIC` exact, verrous de ligne, déclencheurs de protection, sauvegardes éprouvées (`pg_dump`) |
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic | Calcul décimal exact natif (`Decimal`), documentation OpenAPI automatique, écosystème Excel/PDF (openpyxl, reportlab) |
| Interface | React 18, TypeScript, Mantine 7, TanStack Query | Composants professionnels (tableaux, dates, graphiques), réactivité, support RTL pour l'arabe |
| Déploiement | Docker Compose (db, backend, frontend Nginx, backup, scheduler) | Installation identique en local ou dans le cloud |

Next.js a été écarté : l'application est une application de gestion authentifiée sans besoin de référencement ; une SPA servie par Nginx est plus simple à exploiter.

# 2. Organisation du code

```
backend/app/
  models.py            modèle de données unique
  services/            règles métier centralisées
    invoices.py        calcul, validation, statuts, classement
    payments.py        règlements, lettrage, rejets, OD
    ledger.py          grand livre, postes ouverts, balance âgée, encours, concordance
    dunning.py         relances    risk.py   notation    provisions.py  NCT / IFRS 9
    kpi.py             indicateurs forecast.py  IA explicable
    accounting.py      écritures   approvals.py quatre yeux
    reports.py         états       exports.py   Excel / PDF / CSV   imports.py
    params.py          moteur de paramétrage daté
  api/                 points d'entrée REST (contrôle des droits, audit)
  security.py, permissions.py, audit.py
backend/migrations/    schéma versionné + déclencheurs de protection
backend/tests/         tests automatisés (pytest, base PostgreSQL réelle)
frontend/src/          écrans React
```

Les écrans n'effectuent **aucun calcul de référence** : ils affichent ce que renvoie l'API (l'aperçu des totaux en saisie de facture est indicatif).

# 3. API

Documentation interactive : `/api/docs` (Swagger) et `/api/redoc`. Préfixe `/api/v1`. Les montants sont transmis sous forme de **chaînes décimales exactes**.

| Domaine | Points d'entrée principaux |
|---|---|
| Authentification | `POST /auth/login`, `/auth/logout`, `/auth/refresh`, `/auth/change-password`, `GET /auth/me` |
| Clients | `GET/POST /customers`, `GET/PUT /customers/{id}`, `/customers/{id}/ledger`, `/history`, `/open-invoices`, `/status` |
| Factures | `GET/POST /invoices`, `GET/PUT/DELETE /invoices/{id}`, `/validate`, `/classify`, `/write-off-request`, `/settle-difference`, `/impute-credit-note`, `/pdf` |
| Encaissements | `GET/POST /payments`, `/payments/{id}/allocate`, `/auto-allocate`, `/status`, `/cancel-request`, `/receipt`, `POST /allocations/{id}/reverse` |
| Recouvrement | `/dunning/proposals`, `/dunning/actions`, `/dunning/preview`, `/dunning/meta` |
| Balance âgée, risque | `/aging`, `/risk/customers/{id}`, `/risk/recompute`, `/risk/overview` |
| Provisions | `/provisions/campaigns`, `/provisions/lines/{id}`, `/provisions/campaigns/{id}/decide`, `/provisions/loss-rates` |
| Pilotage | `/dashboard`, `/alerts`, `/coherence`, `/ai/forecast`, `/ai/anomalies`, `/ai/priorities`, `/ai/synthesis` |
| États | `/reports`, `/reports/{code}?format=json|xlsx|pdf|csv` |
| Comptabilité | `/accounting/entries`, `/accounting/validate`, `/accounting/export` |
| Contrôle | `/approvals`, `/approvals/{id}/decide`, `/audit`, `/audit/verify` |
| Paramétrage | `/params`, `/tax-rates`, `/payment-methods`, `/currencies`, `/exchange-rates`, `/reference-values`, `/dunning-levels`, `/dunning-templates`, `/users`, `/roles` |
| Imports | `/imports/{invoices|customers}`, `/imports/{kind}/template` |

# 4. Sécurité et contrôle interne

| Exigence | Mise en œuvre |
|---|---|
| Authentification | Mot de passe haché bcrypt (coût 12) ; politique : 10 caractères, majuscule, minuscule, chiffre ; changement imposé à la première connexion |
| Protection contre les attaques par essais | Verrouillage après 5 échecs pendant 15 minutes (paramétrable) ; échecs tracés |
| Sessions | Jeton signé de 30 minutes + session serveur révocable ; expiration après 30 minutes d'inactivité ; déconnexion = révocation ; désactivation d'un compte = fermeture de ses sessions |
| Rôles et permissions | Matrice centralisée vérifiée à chaque appel d'API ; périmètre « portefeuille » pour les commerciaux |
| Séparation des responsabilités | Quatre yeux : plafonds, blocage, passage en perte, annulation de règlement, validation des provisions ; l'administrateur ne valide pas d'opérations financières |
| Traçabilité | Journal d'audit de chaque opération (avant/après, utilisateur, IP, horodatage), chaîné SHA-256, inaltérable (déclencheur) ; vérification d'intégrité à la demande et après restauration |
| Intégrité des données | Déclencheurs PostgreSQL : intangibilité des pièces validées, règlements, affectations, OD, écritures exportées |
| Protection des données | Mots de passe jamais stockés en clair ; secrets en variables d'environnement ; en-têtes HTTP de sécurité ; pièces jointes filtrées par extension et taille, empreinte SHA-256 ; aucune donnée transmise à un service externe |
| Sauvegardes | Quotidiennes (base + pièces), contrôlées, avec empreintes et rétention ; restauration testée |

Recommandations de production : HTTPS obligatoire (certificat sur le serveur frontal), pare-feu limitant l'accès au réseau de l'entreprise ou à un VPN, copie des sauvegardes hors site, revue trimestrielle des habilitations.
