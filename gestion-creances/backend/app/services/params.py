"""Moteur de paramétrage : toutes les règles variables (taux, seuils, comptes,
pondérations) sont lues ici, avec une date d'effet. Aucune valeur fiscale n'est
codée en dur dans les traitements."""
import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Parameter

# Valeurs par défaut utilisées si le paramètre n'existe pas encore en base.
DEFAULTS: dict = {
    "company": {"name": "Mon entreprise", "tax_id": "", "address": "", "city": "Tunis", "phone": "", "email": ""},
    "aging.buckets": [[1, 30], [31, 60], [61, 90], [91, 180], [181, None]],
    "invoice.default_terms_days": 30,
    "invoice.stamp_duty_code": "TIMBRE",
    "invoice.apply_stamp_on_credit_note": False,
    "credit.block_on_limit": False,
    "credit.limit_alert_pct": 90,
    "payment.tolerance_tnd": "1.000",
    "payment.auto_allocate_exclude_disputed": True,
    "payment.clearing_days_default": 2,
    "dunning.preventive_days": 7,
    "dso.method": "COMPTABLE",
    "dso.period_days": 90,
    "kpi.recovery_rate_definition": "EXIGIBLE",
    "kpi.top_n": 5,
    "risk.weights": {
        "overdue_ratio": 20, "max_days_overdue": 20, "avg_delay": 15, "late_frequency": 10,
        "incidents": 15, "limit_overrun": 10, "concentration": 5, "trend": 5,
    },
    "risk.thresholds": {"MODERE": 25, "ELEVE": 50, "CRITIQUE": 75},
    "risk.late_grace_days": 5,
    "provision.statutory_method": "NCT",
    "provision.nct.base": "HT",
    "provision.nct.min_days": 90,
    "provision.nct.grid": [
        {"min_days": 91, "max_days": 180, "rate": 25},
        {"min_days": 181, "max_days": 365, "rate": 50},
        {"min_days": 366, "max_days": None, "rate": 100},
    ],
    "provision.nct.classification_min_rate": {"LITIGIEUSE": 0, "DOUTEUSE": 25},
    "provision.ifrs9.base": "TTC",
    "provision.ifrs9.matrix": {"NON_ECHU": 0.5, "1-30": 1.5, "31-60": 4, "61-90": 8, "91-180": 20, "181+": 50},
    "writeoff.recover_vat": False,
    "import.generate_entries": False,
    "export.csv_separator": ";",
    "export.decimal_comma": True,
    "accounts": {
        "clients": "411", "clients_effets": "413", "clients_douteux": "416", "clients_crediteurs": "419",
        "ventes": "70", "tva_collectee": "4366", "timbre": "4368", "autres_taxes": "4368",
        "banque": "532", "caisse": "54", "cheques_a_encaisser": "5112", "effets_a_encaisser": "5113",
        "retenue_source": "4351", "provision_clients": "491", "dotation_provisions": "6817",
        "reprise_provisions": "7817", "pertes_creances": "634", "ecart_reglement_charge": "658",
        "gain_change": "755", "perte_change": "655",
    },
}


def get_param(db: Session, key: str, as_of: dt.date | None = None):
    as_of = as_of or dt.date.today()
    row = db.execute(
        select(Parameter).where(Parameter.key == key, Parameter.valid_from <= as_of)
        .order_by(Parameter.valid_from.desc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return DEFAULTS.get(key)
    return row.value


def account(db: Session, name: str) -> str:
    accs = get_param(db, "accounts") or {}
    return accs.get(name) or DEFAULTS["accounts"][name]
