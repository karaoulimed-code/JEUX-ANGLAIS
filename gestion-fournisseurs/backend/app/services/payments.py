"""Module 6 — Règlements : préparation, autorisation, décaissement, affectation, rejets, rapprochement bancaire."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from ..models import (BankStatementLine, Invoice, Payment, PaymentAllocation, PaymentRun, Supplier,
                      SupplierBankAccount, TreasuryAccount)
from ..money import D, ZERO, r3
from ..security import BusinessError, Ctx
from . import accounting
from .common import (account, check_period_open, ctx_audit, fx_rate, next_number, setting_dec)
from .invoices import balance, disputed_amount

METHODS = {"virement", "cheque", "especes", "effet", "autre"}
PENDING = ("brouillon", "a_approuver", "approuve")


def planned_amount(db, inv: Invoice, exclude_payment: int | None = None) -> Decimal:
    q = (select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
         .join(Payment, Payment.id == PaymentAllocation.payment_id)
         .where(PaymentAllocation.invoice_id == inv.id, PaymentAllocation.cancelled.is_(False),
                Payment.status.in_(PENDING)))
    if exclude_payment:
        q = q.where(Payment.id != exclude_payment)
    return r3(D(db.scalar(q)))


def payable_amount(db, inv: Invoice, exclude_payment: int | None = None) -> Decimal:
    """Montant encore payable : solde − montants contestés − paiements déjà en préparation."""
    return r3(balance(db, inv) - disputed_amount(db, inv) - planned_amount(db, inv, exclude_payment))


def rs_share(db, inv: Invoice, amount) -> Decimal:
    """Part de retenue à la source correspondant au montant réglé (prorata du TTC).
    Le règlement qui solde la facture prend le reliquat exact (pas d'écart d'arrondi cumulé)."""
    if not D(inv.rs_amount) or not D(inv.total_ttc):
        return ZERO
    already = D(db.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.rs_amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.invoice_id == inv.id, PaymentAllocation.cancelled.is_(False),
               Payment.status.notin_(("annule", "rejete")))))
    if r3(amount) >= balance(db, inv) - planned_amount(db, inv):
        return r3(D(inv.rs_amount) - already)
    return min(r3(D(inv.rs_amount) * D(amount) / D(inv.total_ttc)), r3(D(inv.rs_amount) - already))


def unallocated(db, p: Payment) -> Decimal:
    used = sum((D(a.amount) for a in p.allocations if not a.cancelled), ZERO)
    return r3(D(p.cash_amount) + D(p.rs_amount) - used)


def _treasury_code(ctx: Ctx, p: Payment) -> str:
    if p.treasury_account_id:
        return ctx.db.get(TreasuryAccount, p.treasury_account_id).account_code
    return account(ctx.db, ctx.company_id, "caisse" if p.method == "especes" else "banque")


def create_payment(ctx: Ctx, data: dict) -> tuple[Payment, list[str]]:
    warnings: list[str] = []
    sup = ctx.db.get(Supplier, data["supplier_id"])
    if not sup or sup.company_id != ctx.company_id:
        raise BusinessError("Fournisseur introuvable.", status=404)
    if sup.status == "bloque":
        raise BusinessError("Fournisseur bloqué : aucun paiement possible.", code="fournisseur_bloque")
    method = data["method"]
    if method not in METHODS:
        raise BusinessError("Moyen de paiement inconnu.")
    kind = data.get("kind", "reglement")
    currency = data.get("currency") or sup.currency
    allocs = data.get("allocations") or []
    if kind == "reglement" and not allocs and not D(data.get("unallocated_amount") or 0):
        raise BusinessError("Un règlement doit être affecté à au moins une facture (ou saisir un montant non affecté).")
    bank_acc = None
    if method == "virement":
        bank_acc = ctx.db.get(SupplierBankAccount, data.get("supplier_bank_account_id")) if data.get(
            "supplier_bank_account_id") else ctx.db.scalar(select(SupplierBankAccount).where(
                SupplierBankAccount.supplier_id == sup.id, SupplierBankAccount.status == "verifie",
                SupplierBankAccount.currency == currency))
        if not bank_acc or bank_acc.supplier_id != sup.id:
            raise BusinessError("Virement impossible : aucun RIB vérifié pour ce fournisseur.", code="rib_non_verifie")
        if bank_acc.status != "verifie":
            raise BusinessError("Virement impossible : le RIB sélectionné n'est pas vérifié (contrôle anti-fraude).",
                                code="rib_non_verifie")
    p = Payment(company_id=ctx.company_id, supplier_id=sup.id, kind=kind, method=method,
                treasury_account_id=data.get("treasury_account_id"),
                supplier_bank_account_id=bank_acc.id if bank_acc else None,
                payment_date=data["payment_date"], due_date=data.get("due_date"), reference=data.get("reference"),
                currency=currency, exchange_rate=fx_rate(ctx.db, ctx.company_id, currency, data["payment_date"]),
                cash_amount=ZERO, rs_amount=ZERO, status="brouillon", prepared_by_id=ctx.user.id,
                run_id=data.get("run_id"), notes=data.get("notes"),
                number=next_number(ctx.db, ctx.company_id, "RG", data["payment_date"]))
    ctx.db.add(p)
    ctx.db.flush()
    cash = rs = ZERO
    for a in allocs:
        inv = ctx.db.get(Invoice, a["invoice_id"])
        amount = r3(a["amount"])
        if not inv or inv.company_id != ctx.company_id or inv.supplier_id != sup.id:
            raise BusinessError("Facture introuvable pour ce fournisseur.")
        if inv.workflow_status != "validee" or inv.doc_type == "avoir":
            raise BusinessError(f"{inv.internal_ref} : seule une facture validée peut être réglée.")
        if inv.currency != currency:
            raise BusinessError(f"{inv.internal_ref} : devise de la facture différente de celle du paiement.")
        if amount <= 0:
            raise BusinessError("Montant d'affectation invalide.")
        maxp = payable_amount(ctx.db, inv, exclude_payment=p.id)
        if amount > maxp:
            raise BusinessError(
                f"{inv.internal_ref} : montant {amount} supérieur au montant payable {maxp} "
                f"(solde − litiges − paiements en préparation).", code="sur_paiement")
        a_rs = rs_share(ctx.db, inv, amount) if kind == "reglement" else ZERO
        p.allocations.append(PaymentAllocation(company_id=ctx.company_id, invoice_id=inv.id, amount=amount,
                                               rs_amount=a_rs, allocation_date=p.payment_date))
        cash += amount - a_rs
        rs += a_rs
    extra = r3(D(data.get("unallocated_amount") or 0))
    if extra < 0:
        raise BusinessError("Montant non affecté invalide.")
    p.cash_amount, p.rs_amount = r3(cash + extra), r3(rs + D(data.get("advance_rs_amount") or 0))
    if kind == "avance":
        p.cash_amount = r3(p.cash_amount - D(data.get("advance_rs_amount") or 0))
    if p.cash_amount <= 0:
        raise BusinessError("Montant à décaisser nul.")
    cash_tnd = r3(D(p.cash_amount) * D(p.exchange_rate))
    if method == "especes" and cash_tnd >= setting_dec(ctx.db, ctx.company_id, "seuil_especes"):
        warnings.append(f"Paiement en espèces de {cash_tnd} TND : vérifier le régime fiscal applicable "
                        f"(déductibilité, pénalités) avant décaissement.")
    ctx_audit(ctx, "preparation", "reglement", p.id,
              {"numero": p.number, "montant": p.cash_amount, "rs": p.rs_amount, "avertissements": warnings})
    return p, warnings


def submit_payment(ctx: Ctx, p: Payment) -> Payment:
    if p.status != "brouillon":
        raise BusinessError("Seul un règlement en brouillon peut être soumis.")
    cash_tnd = r3(D(p.cash_amount) * D(p.exchange_rate))
    p.required_approvals = 2 if cash_tnd >= setting_dec(ctx.db, ctx.company_id, "seuil_paiement_double_signature") else 1
    p.status = "a_approuver"
    ctx_audit(ctx, "soumission", "reglement", p.id, {"signatures_requises": p.required_approvals})
    return p


def approve_payment(ctx: Ctx, p: Payment) -> Payment:
    if p.status != "a_approuver":
        raise BusinessError("Le règlement n'est pas en attente d'autorisation.")
    if p.prepared_by_id == ctx.user.id:
        raise BusinessError("Séparation des tâches : celui qui prépare un paiement ne peut pas l'autoriser.",
                            code="separation_taches", status=403)
    if p.approved_by_id is None:
        p.approved_by_id = ctx.user.id
    else:
        if p.approved_by_id == ctx.user.id:
            raise BusinessError("La seconde signature doit émaner d'une autre personne.",
                                code="separation_taches", status=403)
        if ctx.user.role != "dg":
            raise BusinessError("Seconde signature réservée au Directeur général.", code="niveau_insuffisant", status=403)
        p.second_approver_id = ctx.user.id
    n = 1 + (1 if p.second_approver_id else 0)
    if n >= p.required_approvals:
        p.status = "approuve"
    ctx_audit(ctx, "autorisation", "reglement", p.id, {"signature": n, "requises": p.required_approvals})
    return p


def execute_payment(ctx: Ctx, p: Payment, execution_date: date | None = None) -> Payment:
    """Décaissement effectif (émission du chèque/effet, transmission du virement) + écriture comptable."""
    if p.status != "approuve":
        raise BusinessError("Le règlement doit être autorisé avant décaissement.")
    if ctx.user.id in (p.approved_by_id, p.second_approver_id):
        raise BusinessError("Séparation des tâches : l'autorisateur ne peut pas exécuter le décaissement.",
                            code="separation_taches", status=403)
    d = execution_date or p.payment_date
    check_period_open(ctx.db, ctx.company_id, d)
    p.payment_date = d
    p.exchange_rate = fx_rate(ctx.db, ctx.company_id, p.currency, d)
    if p.supplier_bank_account_id:
        acc = ctx.db.get(SupplierBankAccount, p.supplier_bank_account_id)
        if acc.status != "verifie":
            raise BusinessError("Le RIB du fournisseur a été modifié depuis la préparation : nouvelle vérification requise.",
                                code="rib_non_verifie")
    active = [a for a in p.allocations if not a.cancelled]
    for a in active:
        inv = ctx.db.get(Invoice, a.invoice_id)
        if D(a.amount) > balance(ctx.db, inv):
            raise BusinessError(f"{inv.internal_ref} : le solde a changé, montant supérieur au solde restant.")
        a.allocation_date = d
        a.fx_difference_tnd = r3(D(a.amount) * (D(p.exchange_rate) - D(inv.exchange_rate)))
    p.status = "emis"
    p.executed_by_id = ctx.user.id
    accounting.post_payment(ctx, p, active, _treasury_code(ctx, p))
    ctx_audit(ctx, "decaissement", "reglement", p.id, {"date": d, "cours": p.exchange_rate})
    return p


def clear_payment(ctx: Ctx, p: Payment, d: date) -> Payment:
    if p.status != "emis":
        raise BusinessError("Seul un règlement émis peut être constaté au débit bancaire.")
    p.status, p.cleared_date = "debite", d
    if p.method == "effet":
        accounting.post_effet_clearing(ctx, p, d, _treasury_code(ctx, p))
    ctx_audit(ctx, "debit_bancaire", "reglement", p.id, {"date": d})
    return p


def reject_payment(ctx: Ctx, p: Payment, reason: str, d: date | None = None) -> Payment:
    """Chèque rejeté / virement retourné / effet impayé : la dette est rétablie, écritures contre-passées."""
    if p.status not in ("emis", "debite"):
        raise BusinessError("Seul un règlement émis peut être rejeté.")
    d = d or date.today()
    for a in p.allocations:
        a.cancelled = True
    p.status, p.rejection_reason, p.rejected_date = "rejete", reason, d
    accounting.reverse_source(ctx, "reglement", p.id, d, f"Rejet {p.number} : {reason}")
    accounting.reverse_source(ctx, "effet", p.id, d, f"Rejet {p.number} : {reason}")
    ctx_audit(ctx, "rejet", "reglement", p.id, {"motif": reason})
    return p


def cancel_payment(ctx: Ctx, p: Payment, reason: str) -> Payment:
    if p.status not in PENDING:
        raise BusinessError("Un règlement décaissé ne s'annule pas : utilisez « rejet » (chèque/virement retourné).")
    for a in p.allocations:
        a.cancelled = True
    p.status, p.rejection_reason = "annule", reason
    ctx_audit(ctx, "annulation", "reglement", p.id, {"motif": reason})
    return p


def allocate_later(ctx: Ctx, p: Payment, inv: Invoice, amount, d: date) -> PaymentAllocation:
    """Affectation ultérieure d'une avance ou d'un paiement non affecté."""
    amount = r3(amount)
    if p.status not in ("emis", "debite"):
        raise BusinessError("Seul un paiement décaissé peut être affecté.")
    if inv.supplier_id != p.supplier_id or inv.currency != p.currency or inv.workflow_status != "validee":
        raise BusinessError("Facture validée du même fournisseur et de même devise exigée.")
    if amount <= 0 or amount > unallocated(ctx.db, p):
        raise BusinessError(f"Montant supérieur au disponible non affecté ({unallocated(ctx.db, p)}).")
    if amount > balance(ctx.db, inv):
        raise BusinessError("Montant supérieur au solde de la facture.")
    check_period_open(ctx.db, ctx.company_id, d)
    a = PaymentAllocation(company_id=ctx.company_id, payment_id=p.id, invoice_id=inv.id, amount=amount,
                          rs_amount=ZERO, allocation_date=d, deferred=True,
                          fx_difference_tnd=r3(amount * (D(p.exchange_rate) - D(inv.exchange_rate))))
    p.allocations.append(a)
    ctx.db.flush()
    if p.kind == "avance":
        accounting.post_advance_allocation(ctx, p, a, inv)
    elif D(a.fx_difference_tnd):
        # Le non-affecté a été porté au 401 au cours du paiement ; on ramène la dette au cours historique.
        lab = f"Affectation {p.number} sur {inv.internal_ref}"
        fx = D(a.fx_difference_tnd)
        acc = accounting.supplier_account(ctx, inv)
        if fx > 0:
            lines = [(account(ctx.db, ctx.company_id, "perte_change"), None, lab, fx, ZERO),
                     (acc, inv.supplier_id, lab, ZERO, fx)]
        else:
            lines = [(acc, inv.supplier_id, lab, -fx, ZERO),
                     (account(ctx.db, ctx.company_id, "gain_change"), None, lab, ZERO, -fx)]
        accounting._entry(ctx, "OD", d, lab, "affectation", a.id, lines)
    ctx_audit(ctx, "affectation", "reglement", p.id, {"facture": inv.internal_ref, "montant": amount})
    return a


# ------------------------------------------------------------ campagnes de paiement
def create_run(ctx: Ctx, data: dict) -> tuple[PaymentRun, list[Payment], list[str]]:
    run = PaymentRun(company_id=ctx.company_id, planned_date=data["planned_date"],
                     treasury_account_id=data.get("treasury_account_id"), created_by_id=ctx.user.id,
                     notes=data.get("notes"), number=next_number(ctx.db, ctx.company_id, "CP", data["planned_date"]))
    ctx.db.add(run)
    ctx.db.flush()
    by_sup: dict[int, list[dict]] = {}
    for it in data["items"]:
        inv = ctx.db.get(Invoice, it["invoice_id"])
        if not inv or inv.company_id != ctx.company_id:
            raise BusinessError("Facture introuvable.")
        by_sup.setdefault(inv.supplier_id, []).append(
            {"invoice_id": inv.id, "amount": it.get("amount") or payable_amount(ctx.db, inv)})
    pays, warns = [], []
    for sid, allocs in by_sup.items():
        p, w = create_payment(ctx, {"supplier_id": sid, "method": data.get("method", "virement"),
                                    "treasury_account_id": data.get("treasury_account_id"),
                                    "payment_date": data["planned_date"], "allocations": allocs, "run_id": run.id})
        submit_payment(ctx, p)
        pays.append(p)
        warns += w
    run.status = "soumise"
    ctx_audit(ctx, "creation", "campagne_paiement", run.id, {"reglements": [p.number for p in pays]})
    return run, pays, warns


# ------------------------------------------------------------ rapprochement bancaire
def import_statement(ctx: Ctx, treasury_account_id: int, lines: list[dict]) -> dict:
    acc = ctx.db.get(TreasuryAccount, treasury_account_id)
    if not acc or acc.company_id != ctx.company_id:
        raise BusinessError("Compte de trésorerie introuvable.", status=404)
    batch = f"REL-{date.today():%Y%m%d}-{ctx.db.scalar(select(func.count(BankStatementLine.id))) + 1}"
    created = []
    for l in lines:
        bl = BankStatementLine(company_id=ctx.company_id, treasury_account_id=acc.id, import_batch=batch,
                               operation_date=l["operation_date"], label=l["label"],
                               reference=l.get("reference"), amount=r3(l["amount"]))
        ctx.db.add(bl)
        created.append(bl)
    ctx.db.flush()
    matched = auto_match(ctx, acc.id)
    ctx_audit(ctx, "import_releve", "tresorerie", acc.id, {"lignes": len(created), "rapprochees": matched})
    return {"lot": batch, "lignes": len(created), "rapprochees_auto": matched}


def auto_match(ctx: Ctx, treasury_account_id: int) -> int:
    n = 0
    lines = ctx.db.scalars(select(BankStatementLine).where(
        BankStatementLine.treasury_account_id == treasury_account_id,
        BankStatementLine.matched_payment_id.is_(None), BankStatementLine.amount < 0))
    for bl in lines:
        cands = list(ctx.db.scalars(select(Payment).where(
            Payment.company_id == ctx.company_id, Payment.treasury_account_id == treasury_account_id,
            Payment.status == "emis")))
        amt = -D(bl.amount)
        exact = [p for p in cands if r3(D(p.cash_amount) * D(p.exchange_rate)) == amt]
        ref = [p for p in exact if p.reference and bl.reference and p.reference.strip() == bl.reference.strip()]
        near = [p for p in exact if abs((bl.operation_date - p.payment_date).days) <= 45]
        pick = ref[0] if ref else (near[0] if len(near) == 1 else None)
        if pick:
            match_line(ctx, bl, pick)
            n += 1
    return n


def match_line(ctx: Ctx, bl: BankStatementLine, p: Payment) -> None:
    if bl.matched_payment_id:
        raise BusinessError("Ligne de relevé déjà rapprochée.")
    if r3(D(p.cash_amount) * D(p.exchange_rate)) != -D(bl.amount):
        raise BusinessError("Montants différents : rapprochement refusé.")
    bl.matched_payment_id = p.id
    clear_payment(ctx, p, bl.operation_date)


def reconciliation_state(ctx: Ctx, treasury_account_id: int) -> dict:
    acc = ctx.db.get(TreasuryAccount, treasury_account_id)
    lines = list(ctx.db.scalars(select(BankStatementLine).where(BankStatementLine.treasury_account_id == acc.id)))
    bank_balance = r3(D(acc.opening_balance) + sum((D(l.amount) for l in lines), ZERO))
    outstanding = list(ctx.db.scalars(select(Payment).where(
        Payment.treasury_account_id == acc.id, Payment.status == "emis")))
    out_total = r3(sum((D(p.cash_amount) * D(p.exchange_rate) for p in outstanding), ZERO))
    today = date.today()
    return {
        "compte": acc.name, "solde_releve": bank_balance,
        "paiements_emis_non_debites": out_total,
        "solde_disponible_previsionnel": r3(bank_balance - out_total),
        "lignes_non_rapprochees": [
            {"id": l.id, "date": l.operation_date, "libelle": l.label, "reference": l.reference, "montant": l.amount}
            for l in lines if not l.matched_payment_id and D(l.amount) < 0],
        "emis_non_presentes": [
            {"id": p.id, "numero": p.number, "moyen": p.method, "reference": p.reference, "date": p.payment_date,
             "montant_tnd": r3(D(p.cash_amount) * D(p.exchange_rate)), "anciennete_jours": (today - p.payment_date).days}
            for p in outstanding],
    }


def treasury_available(ctx: Ctx) -> Decimal:
    total = ZERO
    for acc in ctx.db.scalars(select(TreasuryAccount).where(
            TreasuryAccount.company_id == ctx.company_id, TreasuryAccount.is_active.is_(True))):
        total += reconciliation_state(ctx, acc.id)["solde_disponible_previsionnel"]
    return r3(total)


_ = timedelta
