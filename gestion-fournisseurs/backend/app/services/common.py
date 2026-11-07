"""Services transverses : journal d'audit, numérotation, paramètres, taux, devises."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AccountMapping, AuditLog, ExchangeRate, Sequence, Setting, TaxRate
from ..money import D, r6
from ..security import BusinessError, Ctx

# Valeurs par défaut des paramètres de gestion (modifiables en base par entreprise)
DEFAULT_SETTINGS: dict[str, tuple[str, str]] = {
    "tolerance_qte_pct": ("0", "Tolérance d'écart sur quantités facturées vs réceptionnées (%)"),
    "tolerance_prix_pct": ("2", "Tolérance d'écart de prix facture vs commande (%)"),
    "tolerance_montant_abs": ("1.000", "Tolérance absolue d'écart de calcul (TND)"),
    "seuil_bc_obligatoire": ("1000.000", "Montant TTC (TND) au-delà duquel une facture sans bon de commande est bloquante"),
    "seuil_validation_n2": ("10000.000", "Montant TTC (TND) exigeant un 2e niveau de validation (DAF)"),
    "seuil_validation_n3": ("100000.000", "Montant TTC (TND) exigeant un 3e niveau de validation (DG)"),
    "seuil_paiement_double_signature": ("50000.000", "Montant décaissé (TND) exigeant une 2e signature (DG)"),
    "seuil_bc_validation_dg": ("50000.000", "Montant TTC (TND) de commande exigeant la validation du DG"),
    "seuil_hausse_prix_pct": ("15", "Hausse de prix unitaire vs historique déclenchant une alerte (%)"),
    "justificatif_obligatoire": ("true", "La pièce justificative est obligatoire pour valider une facture"),
    "validation_fournisseur": ("true", "Un nouveau fournisseur doit être approuvé avant utilisation"),
    "separation_stricte": ("true", "Séparation des tâches stricte (demandeur/valideur/réceptionnaire/payeur)"),
    "seuil_dependance_pct": ("30", "Part des achats 12 mois au-delà de laquelle un fournisseur est jugé en dépendance (%)"),
    "seuil_especes": ("5000.000", "Montant de paiement en espèces déclenchant une alerte fiscale (TND) — à vérifier"),
    "cout_financement_pct": ("10", "Coût annuel du financement court terme (%) utilisé pour arbitrer les escomptes"),
    "date_cloture": ("", "Date de clôture : aucune opération ne peut être datée à cette date ou avant"),
    "jours_alerte_echeance": ("7", "Nombre de jours avant échéance pour l'alerte"),
    "risque_seuil_modere": ("30", "Score de risque à partir duquel le risque est modéré"),
    "risque_seuil_eleve": ("55", "Score de risque à partir duquel le risque est élevé"),
    "risque_seuil_critique": ("75", "Score de risque à partir duquel le risque est critique"),
}

# Plan de comptes (SCE tunisien) — paramétrable, à confirmer par l'expert-comptable de l'entreprise
DEFAULT_ACCOUNTS: dict[str, tuple[str, str]] = {
    "fournisseurs": ("401", "Fournisseurs d'exploitation"),
    "fournisseurs_effets": ("403", "Fournisseurs - effets à payer"),
    "fournisseurs_immo": ("404", "Fournisseurs d'immobilisations"),
    "fournisseurs_fnp": ("408", "Fournisseurs - factures non parvenues"),
    "avances_fournisseurs": ("409", "Fournisseurs débiteurs - avances et acomptes versés"),
    "avoirs_a_recevoir": ("4098", "RRR à obtenir et autres avoirs non encore reçus"),
    "tva_deductible": ("43662", "TVA déductible sur autres biens et services"),
    "tva_deductible_immo": ("43661", "TVA déductible sur immobilisations"),
    "retenue_source": ("432", "État - impôts et taxes retenus à la source"),
    "achats_defaut": ("6061", "Achats non stockés de matières et fournitures"),
    "timbre": ("66", "Impôts, taxes et versements assimilés"),
    "autres_taxes": ("66", "Impôts, taxes et versements assimilés"),
    "perte_change": ("655", "Pertes de change"),
    "gain_change": ("755", "Gains de change"),
    "banque": ("532", "Banques"),
    "caisse": ("54", "Caisse"),
}


def audit(db: Session, company_id: int | None, user, action: str, entity: str,
          entity_id=None, details: dict | None = None, ip: str | None = None) -> AuditLog:
    prev = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    prev_hash = prev.hash if prev else "0" * 64
    ts = datetime.utcnow()
    payload = json.dumps(
        {"c": company_id, "u": getattr(user, "id", None), "a": action, "e": entity,
         "i": str(entity_id) if entity_id is not None else None, "d": details, "t": ts.isoformat()},
        sort_keys=True, default=str,
    )
    h = hashlib.sha256((prev_hash + payload).encode()).hexdigest()
    log = AuditLog(
        company_id=company_id, user_id=getattr(user, "id", None),
        user_label=getattr(user, "email", None), timestamp=ts, action=action, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=json.loads(json.dumps(details, default=str)) if details else None,
        ip=ip, prev_hash=prev_hash, hash=h,
    )
    db.add(log)
    db.flush()
    return log


def verify_audit_chain(db: Session) -> dict:
    prev_hash = "0" * 64
    count = 0
    for log in db.scalars(select(AuditLog).order_by(AuditLog.id)):
        payload = json.dumps(
            {"c": log.company_id, "u": log.user_id, "a": log.action, "e": log.entity,
             "i": log.entity_id, "d": log.details, "t": log.timestamp.isoformat()},
            sort_keys=True, default=str,
        )
        expected = hashlib.sha256((prev_hash + payload).encode()).hexdigest()
        if log.prev_hash != prev_hash or log.hash != expected:
            return {"integre": False, "premiere_rupture_id": log.id, "lignes_controlees": count}
        prev_hash = log.hash
        count += 1
    return {"integre": True, "lignes_controlees": count}


def ctx_audit(ctx: Ctx, action: str, entity: str, entity_id=None, details=None):
    return audit(ctx.db, ctx.company_id, ctx.user, action, entity, entity_id, details, ctx.ip)


def next_number(db: Session, company_id: int, prefix: str, on: date | None = None) -> str:
    year = (on or date.today()).year
    seq = db.scalar(select(Sequence).where(
        Sequence.company_id == company_id, Sequence.prefix == prefix, Sequence.year == year
    ).with_for_update())
    if not seq:
        seq = Sequence(company_id=company_id, prefix=prefix, year=year, last_number=0)
        db.add(seq)
    seq.last_number += 1
    db.flush()
    return f"{prefix}-{year}-{seq.last_number:05d}"


def get_setting(db: Session, company_id: int, key: str) -> str:
    s = db.scalar(select(Setting).where(Setting.company_id == company_id, Setting.key == key))
    if s is not None:
        return s.value
    return DEFAULT_SETTINGS[key][0]


def setting_dec(db: Session, company_id: int, key: str) -> Decimal:
    v = get_setting(db, company_id, key)
    return D(v or "0")


def setting_bool(db: Session, company_id: int, key: str) -> bool:
    return get_setting(db, company_id, key).strip().lower() in ("1", "true", "oui", "yes")


def account(db: Session, company_id: int, key: str) -> str:
    m = db.scalar(select(AccountMapping).where(
        AccountMapping.company_id == company_id, AccountMapping.key == key))
    return m.account_code if m else DEFAULT_ACCOUNTS[key][0]


def check_period_open(db: Session, company_id: int, d: date) -> None:
    lock = get_setting(db, company_id, "date_cloture")
    if lock:
        lock_d = date.fromisoformat(lock)
        if d <= lock_d:
            raise BusinessError(
                f"Période clôturée : aucune opération ne peut être datée au {d:%d/%m/%Y} "
                f"(clôture au {lock_d:%d/%m/%Y}).", code="periode_close")


def tax_rates(db: Session, company_id: int, kind: str, on: date) -> list[TaxRate]:
    q = select(TaxRate).where(
        TaxRate.company_id == company_id, TaxRate.kind == kind, TaxRate.is_active.is_(True),
        TaxRate.valid_from <= on,
    )
    return [t for t in db.scalars(q) if t.valid_to is None or t.valid_to >= on]


def tax_rate_by_code(db: Session, company_id: int, code: str, on: date) -> TaxRate | None:
    for kind in ("RS", "TVA", "TIMBRE", "AUTRE"):
        for t in tax_rates(db, company_id, kind, on):
            if t.code == code:
                return t
    return None


def fx_rate(db: Session, company_id: int, currency: str, on: date) -> Decimal:
    if currency == "TND":
        return Decimal(1)
    fx = db.scalar(select(ExchangeRate).where(
        ExchangeRate.company_id == company_id, ExchangeRate.currency == currency,
        ExchangeRate.rate_date <= on).order_by(ExchangeRate.rate_date.desc()).limit(1))
    if not fx:
        raise BusinessError(
            f"Aucun cours de change {currency} saisi au {on:%d/%m/%Y}. Saisissez le cours (BCT) dans Paramètres > Devises.",
            code="cours_manquant")
    return r6(fx.rate)
