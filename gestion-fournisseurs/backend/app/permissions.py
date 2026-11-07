"""Matrice des rôles et permissions (séparation des responsabilités).

Principe : l'administrateur gère les utilisateurs et le paramétrage technique mais
n'intervient pas dans les opérations (il ne peut ni valider une facture ni payer).
"""

ROLES = {
    "admin": "Administrateur",
    "dg": "Directeur général",
    "daf": "Directeur financier",
    "resp_achats": "Responsable achats",
    "resp_compta": "Responsable comptable",
    "agent_compta": "Agent comptable",
    "tresorier": "Trésorier",
    "lecture": "Consultation seule",
}

ALL = set(ROLES)
OPS = {"dg", "daf", "resp_achats", "resp_compta", "agent_compta", "tresorier"}

PERMISSIONS: dict[str, set[str]] = {
    "read": ALL,
    "supplier.write": {"resp_achats", "resp_compta", "agent_compta"},
    "supplier.approve": {"daf", "resp_compta"},
    "supplier.bank_verify": {"daf", "resp_compta"},
    "supplier.evaluate": {"resp_achats", "daf", "dg"},
    "pr.create": OPS,
    "pr.approve": {"dg", "daf", "resp_achats"},
    "po.create": {"resp_achats"},
    "po.approve": {"dg", "daf"},
    "receipt.create": {"resp_achats", "agent_compta"},
    "invoice.create": {"agent_compta", "resp_compta"},
    "invoice.validate": {"resp_compta", "daf", "dg"},
    "invoice.force": {"daf"},
    "invoice.cancel": {"daf", "resp_compta"},
    "dispute.manage": {"resp_achats", "resp_compta", "agent_compta", "daf"},
    "payment.prepare": {"tresorier", "agent_compta"},
    "payment.approve": {"daf", "dg"},
    "payment.execute": {"tresorier"},
    "bank.reconcile": {"tresorier", "resp_compta"},
    "accounting.read": {"resp_compta", "agent_compta", "daf", "dg", "lecture"},
    "accounting.validate": {"resp_compta"},
    "treasury.read": {"daf", "dg", "tresorier", "resp_compta"},
    "settings.manage": {"admin", "resp_compta"},
    "users.manage": {"admin"},
    "audit.read": {"admin", "dg", "daf", "resp_compta"},
}

# Niveau d'approbation des factures -> rôles habilités
INVOICE_LEVEL_ROLES = {1: {"resp_compta", "daf", "dg"}, 2: {"daf", "dg"}, 3: {"dg"}}


def has_permission(role: str, perm: str) -> bool:
    return role in PERMISSIONS.get(perm, set())


def matrix() -> list[dict]:
    return [
        {"permission": p, **{r: (r in roles) for r in ROLES}} for p, roles in PERMISSIONS.items()
    ]
