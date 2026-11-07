"""Encaissements et lettrage (affectation des crédits aux échéances).

Un « crédit » client est un règlement, un avoir validé ou une OD (écart de
règlement, passage en perte). Chaque affectation met à jour, dans la même
transaction : l'échéance, la facture, le crédit source, l'écart de change et
l'écriture comptable associée.
"""
import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import ZERO, D, q3, q6
from ..models import (Adjustment, Allocation, Customer, Installment, Invoice, Payment, PaymentMethod, User, now_utc)
from . import accounting
from .invoices import get_rate, recompute_invoice
from .params import get_param
from .sequences import next_number


# ------------------------------------------------------------------ sources de crédit
class Source:
    """Adaptateur commun aux trois types de crédits."""

    def __init__(self, obj):
        self.obj = obj

    @property
    def kind(self):
        return "PAYMENT" if isinstance(self.obj, Payment) else ("CREDIT_NOTE" if isinstance(self.obj, Invoice) else "ADJUSTMENT")

    @property
    def customer_id(self):
        return self.obj.customer_id

    @property
    def currency(self):
        return self.obj.currency

    @property
    def rate(self) -> Decimal:
        return self.obj.exchange_rate

    @property
    def total(self) -> Decimal:
        return self.obj.total_ttc if self.kind == "CREDIT_NOTE" else self.obj.amount

    @property
    def total_tnd(self) -> Decimal:
        return self.obj.total_ttc_tnd if self.kind == "CREDIT_NOTE" else self.obj.amount_tnd

    @property
    def used(self) -> Decimal:
        return self.obj.paid_amount if self.kind == "CREDIT_NOTE" else self.obj.allocated_amount

    def add_used(self, amt: Decimal):
        if self.kind == "CREDIT_NOTE":
            self.obj.paid_amount += amt
            self.obj.balance = self.obj.total_ttc - self.obj.paid_amount
        else:
            self.obj.allocated_amount += amt

    @property
    def available(self) -> Decimal:
        return self.total - self.used

    def check_usable(self):
        if self.kind == "PAYMENT" and self.obj.status in ("REJETE", "ANNULE"):
            raise HTTPException(409, "Règlement rejeté ou annulé : affectation impossible")
        if self.kind == "CREDIT_NOTE" and (self.obj.lifecycle != "VALIDEE" or self.obj.doc_type != "AVOIR"):
            raise HTTPException(409, "Seul un avoir validé peut être imputé")

    def fk(self):
        return {"payment_id": self.obj.id} if self.kind == "PAYMENT" else (
            {"credit_note_id": self.obj.id} if self.kind == "CREDIT_NOTE" else {"adjustment_id": self.obj.id})

    def active_allocations(self, db: Session) -> list[Allocation]:
        col = {"PAYMENT": Allocation.payment_id, "CREDIT_NOTE": Allocation.credit_note_id, "ADJUSTMENT": Allocation.adjustment_id}[self.kind]
        return list(db.execute(select(Allocation).where(col == self.obj.id, Allocation.reversed_at.is_(None))).scalars())

    def date(self) -> dt.date:
        return self.obj.receipt_date if self.kind == "PAYMENT" else (self.obj.issue_date if self.kind == "CREDIT_NOTE" else self.obj.date)


# ------------------------------------------------------------------ affectation
def allocate_installment(db: Session, user: User, src: Source, ins: Installment, amount, date: dt.date | None = None) -> Allocation:
    amount = q3(amount)
    inv = ins.invoice
    src.check_usable()
    if amount <= 0:
        raise HTTPException(400, "Montant d'affectation invalide")
    if inv.lifecycle != "VALIDEE" or inv.doc_type != "FACTURE":
        raise HTTPException(409, "Affectation possible uniquement sur une facture validée")
    if inv.customer_id != src.customer_id:
        raise HTTPException(409, "Le crédit et la facture n'appartiennent pas au même client")
    if inv.currency != src.currency:
        raise HTTPException(409, f"Devise différente ({src.currency} / {inv.currency}) : affectation impossible")
    if amount > ins.amount - ins.paid_amount:
        raise HTTPException(409, f"Montant supérieur au reste dû de l'échéance ({ins.amount - ins.paid_amount})")
    if amount > src.available:
        raise HTTPException(409, f"Montant supérieur au disponible du crédit ({src.available})")
    eff_date = max(date or dt.date.today(), src.date(), inv.issue_date)
    # Contre-valeur TND côté facture : la dernière affectation solde exactement l'échéance
    inv_tnd = (ins.amount_tnd - ins.paid_amount_tnd) if amount == ins.amount - ins.paid_amount else q3(amount * inv.exchange_rate)
    # Côté crédit : la dernière affectation solde exactement le crédit
    used_tnd = sum((a.source_amount_tnd for a in src.active_allocations(db)), ZERO)
    src_tnd = (src.total_tnd - used_tnd) if amount == src.available else q3(amount * src.rate)
    a = Allocation(customer_id=inv.customer_id, invoice_id=inv.id, installment_id=ins.id, amount=amount, amount_tnd=inv_tnd,
                   source_amount_tnd=src_tnd, fx_difference_tnd=src_tnd - inv_tnd, allocation_date=eff_date,
                   created_by=user.id, **src.fk())
    a.invoice = inv
    a.installment = ins
    db.add(a)
    ins.paid_amount += amount
    ins.paid_amount_tnd += inv_tnd
    src.add_used(amount)
    recompute_invoice(db, inv)
    db.flush()
    accounting.on_allocation(db, a)
    return a


def allocate_invoice(db: Session, user: User, src: Source, inv: Invoice, amount, date=None) -> list[Allocation]:
    """Répartit un montant sur les échéances de la facture, de la plus ancienne à la plus récente."""
    amount = q3(amount)
    if amount > inv.balance:
        raise HTTPException(409, f"Montant ({amount}) supérieur au solde de la facture {inv.number} ({inv.balance})")
    out = []
    for ins in sorted(inv.installments, key=lambda i: (i.due_date, i.seq)):
        rem = ins.amount - ins.paid_amount
        if amount <= 0:
            break
        if rem <= 0:
            continue
        take = min(rem, amount)
        out.append(allocate_installment(db, user, src, ins, take, date))
        amount -= take
    return out


def open_invoices(db: Session, customer_id: int, currency: str, exclude_disputed: bool) -> list[Invoice]:
    q = (select(Invoice).where(Invoice.customer_id == customer_id, Invoice.doc_type == "FACTURE",
                               Invoice.lifecycle == "VALIDEE", Invoice.balance > 0, Invoice.currency == currency,
                               Invoice.classification != "IRRECOUVRABLE")
         .order_by(Invoice.due_date, Invoice.issue_date, Invoice.id).with_for_update())
    if exclude_disputed:
        q = q.where(Invoice.classification != "LITIGIEUSE")
    return list(db.execute(q).scalars())


def auto_allocate(db: Session, user: User, src: Source, date=None) -> list[Allocation]:
    """Lettrage automatique « première échéance, premier réglé » (FIFO)."""
    out = []
    excl = bool(get_param(db, "payment.auto_allocate_exclude_disputed"))
    for inv in open_invoices(db, src.customer_id, src.currency, excl):
        if src.available <= 0:
            break
        out += allocate_invoice(db, user, src, inv, min(src.available, inv.balance), date)
    return out


def reverse_allocation(db: Session, user: User, a: Allocation, reason: str, date: dt.date | None = None) -> None:
    if a.reversed_at:
        raise HTTPException(409, "Affectation déjà annulée")
    ins = a.installment
    inv = a.invoice
    a.reversed_at = now_utc()
    a.reversed_date = date or dt.date.today()
    if a.reversed_date < a.allocation_date:
        a.reversed_date = a.allocation_date
    a.reversed_by = user.id
    a.reversal_reason = reason[:255]
    ins.paid_amount -= a.amount
    ins.paid_amount_tnd -= a.amount_tnd
    if a.payment_id:
        db.get(Payment, a.payment_id).allocated_amount -= a.amount
    elif a.credit_note_id:
        cn = db.get(Invoice, a.credit_note_id)
        cn.paid_amount -= a.amount
        cn.balance = cn.total_ttc - cn.paid_amount
    else:
        db.get(Adjustment, a.adjustment_id).allocated_amount -= a.amount
    recompute_invoice(db, inv)
    db.flush()
    accounting.on_allocation(db, a, reverse=True)


# ------------------------------------------------------------------ règlements
INITIAL_STATUS = {"CHEQUE": "EN_PORTEFEUILLE", "EFFET": "EN_PORTEFEUILLE"}


def create_payment(db: Session, user: User, data: dict) -> tuple[Payment, list[Allocation]]:
    cust = db.get(Customer, data["customer_id"])
    if not cust:
        raise HTTPException(404, "Client introuvable")
    method = db.get(PaymentMethod, data["method_id"])
    if not method or not method.active:
        raise HTTPException(400, "Moyen de paiement invalide")
    amount = q3(data["amount"])
    if amount <= 0:
        raise HTTPException(400, "Le montant doit être positif")
    if method.kind in ("CHEQUE", "EFFET") and not data.get("reference"):
        raise HTTPException(400, "Le numéro du chèque ou de l'effet est obligatoire")
    if method.kind == "EFFET" and not data.get("value_date"):
        raise HTTPException(400, "La date d'échéance de l'effet est obligatoire")
    receipt = data["receipt_date"]
    if receipt > dt.date.today():
        raise HTTPException(400, "Date de réception future")
    currency = data.get("currency") or "TND"
    rate = q6(data["exchange_rate"]) if data.get("exchange_rate") else get_rate(db, currency, receipt)
    if method.kind == "CHEQUE" and method.requires_clearing and data.get("reference"):
        dup = db.execute(select(Payment).where(Payment.customer_id == cust.id, Payment.reference == data["reference"],
                                               Payment.method_id == method.id, Payment.status != "ANNULE")).first()
        if dup:
            raise HTTPException(409, f"Le chèque n° {data['reference']} est déjà enregistré pour ce client")
    status = INITIAL_STATUS.get(method.kind, "ENCAISSE")
    p = Payment(number=next_number(db, "PAYMENT", receipt.year), customer_id=cust.id, method_id=method.id, method_kind=method.kind,
                receipt_date=receipt, value_date=data.get("value_date") or (receipt + dt.timedelta(days=int(get_param(db, "payment.clearing_days_default") or 0))
                                                       if method.kind in INITIAL_STATUS else receipt),
                amount=amount, currency=currency, exchange_rate=rate, amount_tnd=q3(amount * rate), reference=data.get("reference"),
                bank_name=data.get("bank_name"), drawer=data.get("drawer"), status=status, notes=data.get("notes"),
                created_by=user.id, cleared_date=receipt if status == "ENCAISSE" else None)
    p.customer = cust
    p.method = method
    db.add(p)
    db.flush()
    accounting.on_payment_created(db, p)
    src = Source(p)
    allocs: list[Allocation] = []
    if data.get("allocations"):
        for item in data["allocations"]:
            inv = db.execute(select(Invoice).where(Invoice.id == item["invoice_id"]).with_for_update()).scalar_one_or_none()
            if not inv:
                raise HTTPException(404, f"Facture {item['invoice_id']} introuvable")
            allocs += allocate_invoice(db, user, src, inv, item["amount"], receipt)
    elif data.get("auto_allocate", True):
        allocs = auto_allocate(db, user, src, receipt)
    return p, allocs


TRANSITIONS = {
    "EN_PORTEFEUILLE": {"REMIS", "ENCAISSE", "REJETE"},
    "REMIS": {"ENCAISSE", "REJETE"},
    "ENCAISSE": {"REJETE"},
}


def change_status(db: Session, user: User, p: Payment, new: str, date: dt.date, reason: str | None = None) -> None:
    if new not in TRANSITIONS.get(p.status, set()):
        raise HTTPException(409, f"Transition {p.status} → {new} non autorisée")
    if new == "REJETE" and p.method_kind not in ("CHEQUE", "EFFET"):
        raise HTTPException(409, "Seuls les chèques et effets peuvent être rejetés")
    if date < p.receipt_date:
        raise HTTPException(400, "Date antérieure à la réception du règlement")
    if new == "REMIS":
        p.deposited_date = date
    elif new == "ENCAISSE":
        p.cleared_date = date
    elif new == "REJETE":
        if not reason:
            raise HTTPException(400, "Le motif du rejet est obligatoire")
        for a in Source(p).active_allocations(db):
            reverse_allocation(db, user, a, f"Rejet du règlement : {reason}", date)
        p.rejected_date = date
        p.rejection_reason = reason
    accounting.on_payment_status(db, p, new, date)
    p.status = new


def cancel_payment(db: Session, user: User, p: Payment, reason: str, date: dt.date | None = None) -> None:
    """Annulation (erreur de saisie) : contre-passation tracée, jamais de suppression."""
    if p.status in ("ANNULE", "REJETE"):
        raise HTTPException(409, "Règlement déjà rejeté ou annulé")
    date = date or dt.date.today()
    for a in Source(p).active_allocations(db):
        reverse_allocation(db, user, a, f"Annulation du règlement : {reason}", date)
    accounting.on_payment_status(db, p, "ANNULE", date)
    p.status = "ANNULE"
    p.cancelled_date = date
    p.cancel_reason = reason


def create_adjustment(db: Session, user: User, inv: Invoice, kind: str, amount, reason: str, date: dt.date,
                      approval_id: int | None = None, provision_reversal_tnd=ZERO) -> Adjustment:
    amount = q3(amount)
    if amount <= 0 or amount > inv.balance:
        raise HTTPException(400, "Montant d'OD invalide")
    adj = Adjustment(number=next_number(db, "ADJ", date.year), customer_id=inv.customer_id, kind=kind, date=date, amount=amount,
                     currency=inv.currency, exchange_rate=inv.exchange_rate, amount_tnd=q3(amount * inv.exchange_rate),
                     reason=reason, approval_id=approval_id, created_by=user.id)
    db.add(adj)
    db.flush()
    allocate_invoice(db, user, Source(adj), inv, amount, date)
    accounting.on_adjustment(db, adj, inv, D(provision_reversal_tnd))
    return adj


def settle_small_difference(db: Session, user: User, inv: Invoice, reason: str) -> Adjustment:
    tol = D(get_param(db, "payment.tolerance_tnd"))
    bal_tnd = q3(inv.balance * inv.exchange_rate)
    if inv.balance <= 0:
        raise HTTPException(409, "Facture déjà soldée")
    if bal_tnd > tol:
        raise HTTPException(409, f"Écart de {bal_tnd} TND supérieur à la tolérance ({tol} TND) : demande de passage en perte requise")
    return create_adjustment(db, user, inv, "ECART_REGLEMENT", inv.balance, reason or "Écart de règlement", dt.date.today())


def payment_dict(p: Payment) -> dict:
    return {
        "id": p.id, "number": p.number, "customer_id": p.customer_id, "customer_code": p.customer.code,
        "customer_name": p.customer.legal_name, "method_id": p.method_id, "method_label": p.method.label,
        "method_kind": p.method_kind, "receipt_date": p.receipt_date, "value_date": p.value_date, "amount": p.amount,
        "currency": p.currency, "exchange_rate": p.exchange_rate, "amount_tnd": p.amount_tnd,
        "allocated_amount": p.allocated_amount,
        "unallocated_amount": (p.amount - p.allocated_amount) if p.status not in ("REJETE", "ANNULE") else ZERO,
        "reference": p.reference, "bank_name": p.bank_name, "drawer": p.drawer, "status": p.status,
        "deposited_date": p.deposited_date, "cleared_date": p.cleared_date, "rejected_date": p.rejected_date,
        "rejection_reason": p.rejection_reason, "cancelled_date": p.cancelled_date, "cancel_reason": p.cancel_reason,
        "notes": p.notes, "created_at": p.created_at,
    }
