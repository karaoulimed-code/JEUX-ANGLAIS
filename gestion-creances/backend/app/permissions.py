"""Matrice des rôles et permissions (séparation des responsabilités).

Principes :
- le commercial ne voit que son portefeuille et ne touche pas aux encaissements ;
- l'agent de recouvrement relance mais ne saisit pas d'encaissement ni de provision ;
- la provision est proposée par le comptable et validée par le DAF (deux personnes) ;
- les écritures sont validées puis exportées par la comptabilité ;
- l'administrateur gère les utilisateurs et les paramètres, sans valider d'opérations
  financières (il ne peut pas être juge et partie).
"""

ROLES = {
    "ADMIN": "Administrateur",
    "DAF": "Directeur financier",
    "COMPTABLE": "Responsable comptable",
    "RECOUVREMENT": "Agent de recouvrement",
    "COMMERCIAL": "Commercial",
    "LECTURE": "Consultation seule",
}

READ_ALL = {
    "dashboard.read", "customers.read", "invoices.read", "payments.read", "dunning.read",
    "risk.read", "aging.read", "reports.read", "forecast.read", "provisions.read", "accounting.read",
}

PERMISSIONS: dict[str, set[str]] = {
    "ADMIN": READ_ALL | {"users.manage", "params.read", "params.write", "audit.read", "customers.write"},
    "DAF": READ_ALL | {
        "customers.write", "customers.credit_limit", "invoices.write", "invoices.validate", "invoices.classify",
        "payments.write", "allocations.write", "payments.status", "adjustments.write", "dunning.write",
        "provisions.propose", "provisions.validate", "accounting.validate", "accounting.export",
        "approvals.decide", "params.read", "params.write", "audit.read", "imports.write", "risk.compute",
    },
    "COMPTABLE": READ_ALL | {
        "customers.write", "invoices.write", "invoices.validate", "invoices.classify", "payments.write",
        "allocations.write", "payments.status", "adjustments.write", "provisions.propose",
        "accounting.validate", "accounting.export", "params.read", "imports.write", "risk.compute",
    },
    "RECOUVREMENT": READ_ALL - {"accounting.read", "provisions.read"} | {
        "dunning.write", "invoices.classify", "risk.compute",
    },
    "COMMERCIAL": {"dashboard.read", "customers.read", "invoices.read", "payments.read", "dunning.read",
                   "risk.read", "aging.read", "forecast.read", "customers.write"},
    "LECTURE": set(READ_ALL),
}

# Rôles dont le périmètre est restreint à leur portefeuille de clients
PORTFOLIO_SCOPED = {"COMMERCIAL"}


def has_permission(role: str, perm: str) -> bool:
    return perm in PERMISSIONS.get(role, set())
