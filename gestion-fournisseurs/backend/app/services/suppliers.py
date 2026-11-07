"""Module 1 — Fichier fournisseurs : création, doublons, coordonnées bancaires."""
from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy import select

from ..models import Supplier, SupplierBankAccount
from ..security import BusinessError, Ctx
from .common import ctx_audit, setting_bool

MF_RE = re.compile(r"^\d{7}[A-Z][ABDNP][MCPNE]\d{3}$")
CATEGORIES = {"strategique", "regulier", "occasionnel", "critique", "a_risque"}
STATUSES = {"en_attente", "actif", "bloque", "inactif"}


def normalize_tax_id(mf: str | None) -> str | None:
    if not mf:
        return None
    return re.sub(r"[^0-9A-Z]", "", mf.upper()) or None


def tax_id_warning(mf: str | None) -> str | None:
    n = normalize_tax_id(mf)
    if n and not MF_RE.match(n):
        return ("Format de matricule fiscal inhabituel (attendu : 7 chiffres, clé, code TVA, "
                "catégorie, 3 chiffres — ex. 1234567/A/M/000). À vérifier.")
    return None


def normalize_rib(rib: str | None) -> str | None:
    return re.sub(r"\D", "", rib) if rib else None


def rib_warning(rib: str | None) -> str | None:
    n = normalize_rib(rib)
    if not n:
        return None
    if len(n) != 20:
        return "Le RIB tunisien doit comporter 20 chiffres."
    key = 97 - (int(n[:18]) * 100) % 97
    if key != int(n[18:]):
        return "Clé RIB incohérente : vérifier le RIB auprès du fournisseur (appel de contre-vérification)."
    return None


def _name_key(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\b(sarl|suarl|sa|sas|ste|société|societe|ets|etablissements?)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def find_duplicates(ctx: Ctx, legal_name: str, tax_id: str | None, rib: str | None = None,
                    exclude_id: int | None = None) -> list[dict]:
    out = []
    n_mf = normalize_tax_id(tax_id)
    n_rib = normalize_rib(rib)
    key = _name_key(legal_name)
    for s in ctx.db.scalars(select(Supplier).where(Supplier.company_id == ctx.company_id)):
        if s.id == exclude_id:
            continue
        reasons = []
        if n_mf and s.tax_id_normalized == n_mf:
            reasons.append("matricule fiscal identique")
        ratio = SequenceMatcher(None, key, _name_key(s.legal_name)).ratio()
        if ratio >= 0.88:
            reasons.append(f"raison sociale proche ({ratio:.0%})")
        if n_rib:
            for b in s.bank_accounts:
                if normalize_rib(b.rib) == n_rib and b.status != "remplace":
                    reasons.append("RIB identique")
        if reasons:
            out.append({"id": s.id, "code": s.code, "legal_name": s.legal_name, "motifs": reasons})
    return out


def create_supplier(ctx: Ctx, data: dict, force: bool = False) -> tuple[Supplier, list[str]]:
    warnings = []
    if data.get("category", "regulier") not in CATEGORIES:
        raise BusinessError("Catégorie de fournisseur inconnue.")
    dups = find_duplicates(ctx, data["legal_name"], data.get("tax_id"))
    hard = [d for d in dups if "matricule fiscal identique" in d["motifs"]]
    if hard and not force:
        raise BusinessError("Fournisseur probablement en double (même matricule fiscal).",
                            code="doublon_fournisseur", status=409, data=dups)
    if dups:
        warnings.append("Doublons potentiels : " + ", ".join(f"{d['code']} ({'; '.join(d['motifs'])})" for d in dups))
    w = tax_id_warning(data.get("tax_id"))
    if w:
        warnings.append(w)
    exists = ctx.db.scalar(select(Supplier).where(
        Supplier.company_id == ctx.company_id, Supplier.code == data["code"]))
    if exists:
        raise BusinessError(f"Le code fournisseur {data['code']} existe déjà.", status=409)
    s = Supplier(company_id=ctx.company_id, created_by_id=ctx.user.id, **data)
    s.tax_id_normalized = normalize_tax_id(s.tax_id)
    s.status = "en_attente" if setting_bool(ctx.db, ctx.company_id, "validation_fournisseur") else "actif"
    ctx.db.add(s)
    ctx.db.flush()
    ctx_audit(ctx, "creation", "fournisseur", s.id, {"code": s.code, "avertissements": warnings, "force": force})
    return s, warnings


SENSITIVE = {"tax_id", "legal_name", "status", "credit_limit", "payment_terms_days", "rs_code", "vat_regime"}


def update_supplier(ctx: Ctx, s: Supplier, data: dict) -> Supplier:
    before = {}
    for k, v in data.items():
        if k in ("id", "company_id", "status", "approved_by_id", "created_by_id"):
            continue
        old = getattr(s, k)
        if old != v:
            before[k] = {"avant": old, "apres": v}
            setattr(s, k, v)
    if "tax_id" in data:
        s.tax_id_normalized = normalize_tax_id(s.tax_id)
    ctx_audit(ctx, "modification", "fournisseur", s.id, before)
    return s


def approve_supplier(ctx: Ctx, s: Supplier, status: str) -> Supplier:
    if status not in STATUSES:
        raise BusinessError("Statut inconnu.")
    if status == "actif" and s.created_by_id == ctx.user.id and setting_bool(ctx.db, ctx.company_id, "separation_stricte"):
        raise BusinessError("Séparation des tâches : le créateur d'un fournisseur ne peut pas l'approuver.",
                            code="separation_taches", status=403)
    old = s.status
    s.status = status
    if status == "actif":
        s.approved_by_id, s.approved_at = ctx.user.id, datetime.utcnow()
    ctx_audit(ctx, "changement_statut", "fournisseur", s.id, {"avant": old, "apres": status})
    return s


def add_bank_account(ctx: Ctx, s: Supplier, data: dict) -> tuple[SupplierBankAccount, list[str]]:
    warnings = []
    w = rib_warning(data.get("rib"))
    if w:
        warnings.append(w)
    n_rib = normalize_rib(data.get("rib"))
    if n_rib:
        for other in ctx.db.scalars(select(SupplierBankAccount).where(
                SupplierBankAccount.company_id == ctx.company_id,
                SupplierBankAccount.supplier_id != s.id, SupplierBankAccount.status != "remplace")):
            if normalize_rib(other.rib) == n_rib:
                warnings.append(f"ALERTE FRAUDE : ce RIB est déjà attribué au fournisseur #{other.supplier_id}.")
    # tout nouveau RIB remplace les précédents actifs de même devise et doit être vérifié
    for b in ctx.db.scalars(select(SupplierBankAccount).where(SupplierBankAccount.supplier_id == s.id)):
        if b.status in ("a_verifier", "verifie") and b.currency == data.get("currency", "TND"):
            b.status = "remplace"
    acc = SupplierBankAccount(company_id=ctx.company_id, created_by_id=ctx.user.id, status="a_verifier", **data)
    acc.supplier = s
    if acc.rib:
        acc.rib = normalize_rib(acc.rib)
    ctx.db.add(acc)
    ctx.db.flush()
    ctx_audit(ctx, "ajout_rib", "fournisseur", s.id,
              {"compte_id": acc.id, "banque": acc.bank_name, "rib_fin": (acc.rib or acc.iban or "")[-4:],
               "avertissements": warnings})
    return acc, warnings


def verify_bank_account(ctx: Ctx, acc: SupplierBankAccount, accept: bool, note: str | None) -> SupplierBankAccount:
    if acc.status != "a_verifier":
        raise BusinessError("Ce compte n'est pas en attente de vérification.")
    if acc.created_by_id == ctx.user.id:
        raise BusinessError("Séparation des tâches : la personne qui saisit un RIB ne peut pas le vérifier.",
                            code="separation_taches", status=403)
    acc.status = "verifie" if accept else "rejete"
    acc.verified_by_id, acc.verified_at, acc.verification_note = ctx.user.id, datetime.utcnow(), note
    ctx_audit(ctx, "verification_rib", "fournisseur", acc.supplier_id,
              {"compte_id": acc.id, "decision": acc.status, "note": note})
    return acc
