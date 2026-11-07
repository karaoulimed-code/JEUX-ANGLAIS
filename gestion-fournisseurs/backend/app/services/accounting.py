"""Module 9 — Écritures comptables proposées, validation, contre-passation, rapprochement auxiliaire / général.

Les schémas d'écritures utilisent les comptes paramétrés (table account_mappings).
Montants en TND (monnaie de tenue). Toute écriture est équilibrée (contrôle bloquant).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from ..models import (Invoice, JournalEntry, JournalLine, Payment, Supplier)
from ..money import D, ZERO, r3
from ..security import BusinessError, Ctx
from .common import account, check_period_open, ctx_audit, next_number


def _entry(ctx: Ctx, journal: str, d: date, label: str, source_type: str, source_id: int,
           lines: list[tuple[str, int | None, str, Decimal, Decimal]], reversal_of: int | None = None) -> JournalEntry:
    lines = [(a, s, l, r3(dr), r3(cr)) for a, s, l, dr, cr in lines if r3(dr) != 0 or r3(cr) != 0]
    tdr = sum((l[3] for l in lines), ZERO)
    tcr = sum((l[4] for l in lines), ZERO)
    if tdr != tcr:
        # écart d'arrondi de conversion (≤ 0,005 TND) : affecté au compte d'écart de change
        diff = tdr - tcr
        if abs(diff) > Decimal("0.005") * max(len(lines), 1):
            raise BusinessError(f"Écriture déséquilibrée ({tdr} / {tcr}).", code="ecriture_desequilibree")
        if diff > 0:
            lines.append((account(ctx.db, ctx.company_id, "gain_change"), None, "Écart d'arrondi", ZERO, diff))
        else:
            lines.append((account(ctx.db, ctx.company_id, "perte_change"), None, "Écart d'arrondi", -diff, ZERO))
    je = JournalEntry(company_id=ctx.company_id, journal=journal, entry_date=d, label=label,
                      number=next_number(ctx.db, ctx.company_id, journal, d), source_type=source_type,
                      source_id=source_id, status="proposee", reversal_of_id=reversal_of)
    je.lines = [JournalLine(account_code=a, supplier_id=s, label=l, debit=dr, credit=cr) for a, s, l, dr, cr in lines]
    ctx.db.add(je)
    ctx.db.flush()
    return je


def supplier_account(ctx: Ctx, inv: Invoice) -> str:
    if any((l.account_code or "").startswith("2") for l in inv.lines):
        return account(ctx.db, ctx.company_id, "fournisseurs_immo")
    return account(ctx.db, ctx.company_id, "fournisseurs")


def post_invoice(ctx: Ctx, inv: Invoice) -> JournalEntry:
    """Facture : D charges/immobilisations HT + D TVA déductible + D taxes / C fournisseur TTC.
    Avoir : sens inverse. Acompte : D 409 (HT) au lieu des charges."""
    cid, rate = ctx.company_id, D(inv.exchange_rate)
    sup = ctx.db.get(Supplier, inv.supplier_id)
    lab = f"{inv.internal_ref} {sup.legal_name} n°{inv.supplier_number}"
    lines = []
    for l in inv.lines:
        lines.append((l.account_code, None, lab, D(l.amount_ht) * rate, ZERO))
        tva_acc = account(ctx.db, cid, "tva_deductible_immo" if (l.account_code or "").startswith("2") else "tva_deductible")
        lines.append((tva_acc, None, lab + " TVA", D(l.amount_tva) * rate, ZERO))
    lines.append((account(ctx.db, cid, "timbre"), None, lab + " timbre", D(inv.stamp_duty) * rate, ZERO))
    lines.append((account(ctx.db, cid, "autres_taxes"), None, lab + " autres taxes", D(inv.other_taxes) * rate, ZERO))
    lines.append((supplier_account(ctx, inv), sup.id, lab, ZERO, D(inv.total_ttc_tnd)))
    if inv.doc_type == "avoir":
        lines = [(a, s, l, cr, dr) for a, s, l, dr, cr in lines]
    return _entry(ctx, "ACH", inv.invoice_date, lab, "facture", inv.id, lines)


def post_payment(ctx: Ctx, p: Payment, allocations, treasury_code: str) -> JournalEntry:
    """Règlement : D 401 (au cours historique des factures) / C banque (cash) / C 432 (RS) ± écart de change.
    Avance : D 409. Effet : C 403 (puis 403 -> banque à l'échéance)."""
    cid = ctx.company_id
    sup = ctx.db.get(Supplier, p.supplier_id)
    lab = f"{p.number} {sup.legal_name} {p.method} {p.reference or ''}".strip()
    rate = D(p.exchange_rate)
    lines = []
    total_alloc = ZERO
    for a in allocations:
        inv = ctx.db.get(Invoice, a.invoice_id)
        lines.append((supplier_account(ctx, inv), sup.id, f"{lab} / {inv.internal_ref}",
                      D(a.amount) * D(inv.exchange_rate), ZERO))
        fx = D(a.fx_difference_tnd)
        if fx > 0:
            lines.append((account(ctx.db, cid, "perte_change"), None, f"Perte de change {inv.internal_ref}", fx, ZERO))
        elif fx < 0:
            lines.append((account(ctx.db, cid, "gain_change"), None, f"Gain de change {inv.internal_ref}", ZERO, -fx))
        total_alloc += D(a.amount)
    rest = D(p.cash_amount) + D(p.rs_amount) - total_alloc
    if rest > 0:
        key = "avances_fournisseurs" if p.kind == "avance" else "fournisseurs"
        lines.append((account(ctx.db, cid, key), sup.id, f"{lab} (non affecté)", rest * rate, ZERO))
    credit_acc = account(ctx.db, cid, "fournisseurs_effets") if p.method == "effet" else treasury_code
    lines.append((credit_acc, sup.id if p.method == "effet" else None, lab, ZERO, D(p.cash_amount) * rate))
    lines.append((account(ctx.db, cid, "retenue_source"), None, f"RS {lab}", ZERO, D(p.rs_amount) * rate))
    return _entry(ctx, "REG", p.payment_date, lab, "reglement", p.id, lines)


def post_effet_clearing(ctx: Ctx, p: Payment, d: date, treasury_code: str) -> JournalEntry:
    amt = D(p.cash_amount) * D(p.exchange_rate)
    lab = f"Échéance effet {p.reference or p.number}"
    return _entry(ctx, "REG", d, lab, "effet", p.id, [
        (account(ctx.db, ctx.company_id, "fournisseurs_effets"), p.supplier_id, lab, amt, ZERO),
        (treasury_code, None, lab, ZERO, amt)])


def post_advance_allocation(ctx: Ctx, p: Payment, alloc, inv: Invoice) -> JournalEntry:
    """Imputation d'une avance (409) sur une facture : D 401 / C 409."""
    lab = f"Imputation avance {p.number} sur {inv.internal_ref}"
    amt_hist = D(alloc.amount) * D(inv.exchange_rate)
    amt_pay = D(alloc.amount) * D(p.exchange_rate)
    lines = [(supplier_account(ctx, inv), inv.supplier_id, lab, amt_hist, ZERO),
             (account(ctx.db, ctx.company_id, "avances_fournisseurs"), inv.supplier_id, lab, ZERO, amt_pay)]
    fx = amt_pay - amt_hist
    if fx > 0:
        lines.append((account(ctx.db, ctx.company_id, "perte_change"), None, lab, fx, ZERO))
    elif fx < 0:
        lines.append((account(ctx.db, ctx.company_id, "gain_change"), None, lab, ZERO, -fx))
    return _entry(ctx, "OD", alloc.allocation_date, lab, "imputation_avance", alloc.id, lines)


def post_acompte_imputation(ctx: Ctx, ca, src: Invoice, target: Invoice) -> JournalEntry:
    """Facture d'acompte imputée sur facture définitive : D 401 / C 409 (HT) / C TVA déductible (TVA)."""
    base = D(src.total_ht) + D(src.total_tva)
    ht_part = r3(D(ca.amount) * D(src.total_ht) / base) if base else D(ca.amount)
    tva_part = D(ca.amount) - ht_part
    rate = D(src.exchange_rate)
    lab = f"Imputation acompte {src.internal_ref} sur {target.internal_ref}"
    return _entry(ctx, "OD", ca.allocation_date, lab, "imputation_acompte", ca.id, [
        (supplier_account(ctx, target), target.supplier_id, lab, D(ca.amount) * rate, ZERO),
        (account(ctx.db, ctx.company_id, "avances_fournisseurs"), src.supplier_id, lab, ZERO, ht_part * rate),
        (account(ctx.db, ctx.company_id, "tva_deductible"), None, lab, ZERO, tva_part * rate)])


def reverse_source(ctx: Ctx, source_type: str, source_id: int, d: date, label: str) -> list[JournalEntry]:
    """Contre-passation de toutes les écritures d'une pièce (jamais de suppression)."""
    out = []
    for je in ctx.db.scalars(select(JournalEntry).where(
            JournalEntry.company_id == ctx.company_id, JournalEntry.source_type == source_type,
            JournalEntry.source_id == source_id, JournalEntry.reversal_of_id.is_(None))):
        already = ctx.db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.reversal_of_id == je.id))
        if already:
            continue
        out.append(_entry(ctx, je.journal, d, label, source_type, source_id,
                          [(l.account_code, l.supplier_id, "Contre-passation " + l.label, D(l.credit), D(l.debit))
                           for l in je.lines], reversal_of=je.id))
    return out


def validate_entries(ctx: Ctx, ids: list[int]) -> int:
    n = 0
    for je in ctx.db.scalars(select(JournalEntry).where(
            JournalEntry.company_id == ctx.company_id, JournalEntry.id.in_(ids))):
        if je.status == "validee":
            continue
        check_period_open(ctx.db, ctx.company_id, je.entry_date)
        tdr = sum((D(l.debit) for l in je.lines), ZERO)
        tcr = sum((D(l.credit) for l in je.lines), ZERO)
        if tdr != tcr:
            raise BusinessError(f"Écriture {je.number} déséquilibrée.")
        je.status, je.validated_by_id, je.validated_at = "validee", ctx.user.id, datetime.utcnow()
        n += 1
    ctx_audit(ctx, "validation_ecritures", "ecriture", None, {"ids": ids, "nombre": n})
    return n


def account_balance(ctx: Ctx, prefix: str, as_of: date | None = None, only_validated: bool = False,
                    supplier_id: int | None = None) -> Decimal:
    q = (select(func.coalesce(func.sum(JournalLine.credit), 0) - func.coalesce(func.sum(JournalLine.debit), 0))
         .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
         .where(JournalEntry.company_id == ctx.company_id, JournalLine.account_code.like(prefix + "%")))
    if as_of:
        q = q.where(JournalEntry.entry_date <= as_of)
    if only_validated:
        q = q.where(JournalEntry.status == "validee")
    if supplier_id:
        q = q.where(JournalLine.supplier_id == supplier_id)
    return r3(D(ctx.db.scalar(q)))
