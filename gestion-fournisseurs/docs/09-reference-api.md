# Référence de l'API

_Générée depuis le schéma OpenAPI (`python scripts/api_doc.py`). Documentation interactive et essais en ligne : `/api/docs` (Swagger) et `/api/redoc`._

Authentification : `POST /api/auth/login` renvoie un jeton à transmettre dans l'en-tête `Authorization: Bearer <jeton>`. Les erreurs métier renvoient `422` avec `{detail, code}` ; un droit insuffisant `403`.

## Authentification et utilisateurs

| Méthode | Chemin | Fonction |
|---|---|---|
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/me` | Me |
| POST | `/api/auth/password` | Change Password |
| GET | `/api/auth/roles` | Roles |
| GET | `/api/auth/users` | List Users |
| POST | `/api/auth/users` | Create User |
| PATCH | `/api/auth/users/{uid}` | Update User |

## Module 1 - Fournisseurs

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/suppliers` | List Suppliers |
| POST | `/api/suppliers` | Create Supplier |
| GET | `/api/suppliers/analysis/risk` | Risk |
| POST | `/api/suppliers/bank-accounts/{aid}/verify` | Verify Bank |
| POST | `/api/suppliers/check-duplicates` | Check Duplicates |
| GET | `/api/suppliers/{sid}` | Get Supplier |
| PATCH | `/api/suppliers/{sid}` | Update Supplier |
| POST | `/api/suppliers/{sid}/bank-accounts` | Add Bank |
| POST | `/api/suppliers/{sid}/contracts` | Add Contract |
| POST | `/api/suppliers/{sid}/evaluations` | Add Evaluation |
| POST | `/api/suppliers/{sid}/incidents` | Add Incident |
| POST | `/api/suppliers/{sid}/status` | Set Status |

## Module 2 - Achats et engagements

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/purchasing/commitments` | Commitments |
| GET | `/api/purchasing/orders` | List Orders |
| POST | `/api/purchasing/orders` | Create Order |
| GET | `/api/purchasing/orders/{oid}` | Get Order |
| PATCH | `/api/purchasing/orders/{oid}` | Modify Order |
| POST | `/api/purchasing/orders/{oid}/cancel` | Cancel Order |
| POST | `/api/purchasing/orders/{oid}/close` | Close Order |
| POST | `/api/purchasing/orders/{oid}/decision` | Approve Order |
| POST | `/api/purchasing/orders/{oid}/submit` | Submit Order |
| GET | `/api/purchasing/receipts` | List Receipts |
| POST | `/api/purchasing/receipts` | Create Receipt |
| GET | `/api/purchasing/received-not-invoiced` | Received Not Invoiced |
| GET | `/api/purchasing/requests` | List Requests |
| POST | `/api/purchasing/requests` | Create Request |
| POST | `/api/purchasing/requests/{rid}/decision` | Decide Request |
| POST | `/api/purchasing/requests/{rid}/submit` | Submit Request |

## Module 6 - Comptes de trésorerie et rapprochement bancaire

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/treasury/accounts` | Accounts |
| POST | `/api/treasury/accounts` | Create Account |
| GET | `/api/treasury/accounts/{aid}/reconciliation` | Reconciliation |
| POST | `/api/treasury/match` | Match |
| POST | `/api/treasury/statements` | Import Statement |

## Module 6 - Règlements et trésorerie

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/payments` | List Payments |
| POST | `/api/payments` | Create Payment |
| GET | `/api/payments/plan` | Plan |
| GET | `/api/payments/runs` | List Runs |
| POST | `/api/payments/runs` | Create Run |
| POST | `/api/payments/runs/{rid}/approve` | Approve Run |
| GET | `/api/payments/{pid}` | Get Payment |
| POST | `/api/payments/{pid}/allocate` | Allocate |
| POST | `/api/payments/{pid}/approve` | Approve |
| POST | `/api/payments/{pid}/cancel` | Cancel |
| POST | `/api/payments/{pid}/execute` | Execute |
| POST | `/api/payments/{pid}/reject` | Reject |
| POST | `/api/payments/{pid}/submit` | Submit |

## Module 7 - Litiges

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/disputes` | List Disputes |
| POST | `/api/disputes` | Create Dispute |
| PATCH | `/api/disputes/{did}` | Update Dispute |

## Module 9 - Comptabilité

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/accounting/balances` | Balances |
| GET | `/api/accounting/closing/fnp` | Fnp |
| POST | `/api/accounting/closing/fnp` | Post Fnp |
| GET | `/api/accounting/closing/fx-revaluation` | Fx Revaluation |
| POST | `/api/accounting/closing/fx-revaluation` | Post Fx Revaluation |
| GET | `/api/accounting/entries` | Entries |
| POST | `/api/accounting/entries/validate` | Validate |
| GET | `/api/accounting/export` | Export |
| GET | `/api/accounting/reconciliation` | Reconciliation |

## Modules 3, 4, 7 - Factures, contrôles, avoirs

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/invoices` | List Invoices |
| POST | `/api/invoices` | Create Invoice |
| POST | `/api/invoices/credit-allocations` | Credit Allocation |
| POST | `/api/invoices/import` | Import Invoices |
| GET | `/api/invoices/import/template` | Import Template |
| POST | `/api/invoices/ocr` | Ocr |
| GET | `/api/invoices/{iid}` | Get Invoice |
| PATCH | `/api/invoices/{iid}` | Update Invoice |
| POST | `/api/invoices/{iid}/approve` | Approve |
| POST | `/api/invoices/{iid}/cancel` | Cancel |
| POST | `/api/invoices/{iid}/controls` | Rerun Controls |
| POST | `/api/invoices/{iid}/reject` | Reject |
| POST | `/api/invoices/{iid}/submit` | Submit |

## Modules 5, 10, 11 - Échéancier, pilotage, reporting

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/reports/aging` | Aging |
| GET | `/api/reports/alerts` | Alerts |
| GET | `/api/reports/catalog` | Catalog |
| GET | `/api/reports/dashboard` | Dashboard |
| GET | `/api/reports/export/{name}` | Export |
| GET | `/api/reports/forecast` | Forecast |
| GET | `/api/reports/kpis` | Kpis |
| GET | `/api/reports/ledger` | Ledger |
| GET | `/api/reports/search` | Search |
| GET | `/api/reports/trial-balance` | Trial Balance |

## Paramétrage, audit

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/admin/accounts` | List Accounts |
| PUT | `/api/admin/accounts/{key}` | Set Account |
| GET | `/api/admin/audit` | Audit Logs |
| GET | `/api/admin/audit/verify` | Audit Verify |
| GET | `/api/admin/company` | Company |
| GET | `/api/admin/fx-rates` | List Fx |
| POST | `/api/admin/fx-rates` | Add Fx |
| GET | `/api/admin/settings` | List Settings |
| PUT | `/api/admin/settings/{key}` | Set Setting |
| GET | `/api/admin/tax-rates` | List Rates |
| POST | `/api/admin/tax-rates` | Add Rate |
| PATCH | `/api/admin/tax-rates/{tid}` | Update Rate |

## Pièces justificatives

| Méthode | Chemin | Fonction |
|---|---|---|
| POST | `/api/attachments` | Upload |
| GET | `/api/attachments/{aid}` | Download |

## Système

| Méthode | Chemin | Fonction |
|---|---|---|
| GET | `/api/health` | Health |
