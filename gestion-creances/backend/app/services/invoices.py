"""Factures, avoirs et échéances."""
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..money import ZERO, D, q3, q6
from ..models import (Customer, ExchangeRate, Installment, Invoice, InvoiceLine, InvoiceTax, TaxRate, User, now_utc)
from . import accounting
from .params import get_param
from .sequences import next_number

SETTLEMENT_LABELS = {
    "BROUILLON": "Brouillon", "VALIDEE": "Validée", "NON_ECHUE": "Non échue",
    "PARTIELLEMENT_REGLEE": "Partiellement réglée", "REGLEE": "Réglée", "EN_RETARD": "En retard",
    "LITIGIEUSE": "Litigieuse", "DOUTEUSE": "Douteuse", "IRRECOUVRABLE": "Irrécouvrable",
    "IMPUTE": "Imputé", "NON_IMPUTE": "Non imputé", "PARTIELLEMENT_IMPUTE": "Partiellement imputé",
}


def settlement_status(inv: Invoice, as_of: dt.date | None = None) -> str:
    """Statut calculé à la volée (jamais périmé) à partir des soldes réels.
    Priorité : Brouillon > Irrécouvrable > Réglée > Douteuse > Litigieuse > En retard
    > Partiellement réglée > Non échue."""
    as_of = as_of or dt.date.today()
    if inv.lifecycle == "BROUILLON":
        return "BROUILLON"
    if inv.doc_type == "AVOIR":
        if inv.balance <= 0:
            return "IMPUTE"
        return "PARTIELLEMENT_IMPUTE" if inv.paid_amount > 0 else "NON_IMPUTE"
    if inv.classification == "IRRECOUVRABLE":
        return "IRRECOUVRABLE"
    if inv.balance <= 0:
        return "REGLEE"
    if inv.classification in ("DOUTEUSE", "LITIGIEUSE"):
        return inv.classification
    if any(i.due_date < as_of and i.amount - i.paid_amount > 0 for i in inv.installments):
        return "EN_RETARD"
    if inv.paid_amount > 0:
        return "PARTIELLEMENT_REGLEE"
    return "NON_ECHUE"


def status_filter(status: str, as_of: dt.date):
    """Traduction SQL du statut calculé, pour filtrer les listes."""
    overdue = select(Installment.id).where(Installment.invoice_id == Invoice.id, Installment.due_date < as_of,
                                           Installment.amount > Installment.paid_amount).exists()
    open_ = and_(Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE", Invoice.balance > 0)
    m = {
        "BROUILLON": Invoice.lifecycle == "BROUILLON",
        "VALIDEE": Invoice.lifecycle == "VALIDEE",
        "IRRECOUVRABLE": Invoice.classification == "IRRECOUVRABLE",
        "REGLEE": and_(Invoice.lifecycle == "VALIDEE", Invoice.balance <= 0, Invoice.classification != "IRRECOUVRABLE"),
        "DOUTEUSE": and_(open_, Invoice.classification == "DOUTEUSE"),
        "LITIGIEUSE": and_(open_, Invoice.classification == "LITIGIEUSE"),
        "EN_RETARD": and_(open_, Invoice.classification == "NORMALE", overdue),
        "PARTIELLEMENT_REGLEE": and_(open_, Invoice.classification == "NORMALE", ~overdue, Invoice.paid_amount > 0),
        "NON_ECHUE": and_(open_, Invoice.classification == "NORMALE", ~overdue, Invoice.paid_amount == 0),
        "OUVERTE": open_,
    }
    if status not in m:
        raise HTTPException(400, f"Statut inconnu : {status}")
    return m[status]


def get_rate(db: Session, currency: str, date: dt.date) -> Decimal:
    if currency == "TND":
        return Decimal("1")
    r = db.execute(select(ExchangeRate).where(ExchangeRate.currency == currency, ExchangeRate.date <= date)
                   .order_by(ExchangeRate.date.desc()).limit(1)).scalar_one_or_none()
    if not r:
        raise HTTPException(400, f"Aucun cours de change {currency} disponible au {date:%d/%m/%Y}")
    return r.rate


def _active_tax(db: Session, code: str, date: dt.date) -> TaxRate:
    t = db.execute(select(TaxRate).where(TaxRate.code == code, TaxRate.active.is_(True), TaxRate.valid_from <= date,
                                         or_(TaxRate.valid_to.is_(None), TaxRate.valid_to >= date))
                   .order_by(TaxRate.valid_from.desc()).limit(1)).scalar_one_or_none()
    if not t:
        raise HTTPException(400, f"Taxe « {code} » inexistante ou non applicable au {date:%d/%m/%Y}")
    return t


def compute(db: Session, inv: Invoice, lines: list[dict], other_tax_codes: list[str], apply_stamp: bool) -> None:
    """Calcule HT, TVA par taux, autres taxes et TTC. Les taux sont lus dans le
    paramétrage à la date de la facture (jamais codés en dur)."""
    if not lines:
        raise HTTPException(400, "La facture doit comporter au moins une ligne")
    inv.lines.clear()
    inv.taxes.clear()
    others = [_active_tax(db, c, inv.issue_date) for c in other_tax_codes]
    in_base_pct = sum((D(t.rate) for t in others if t.kind == "AUTRE" and t.rate and t.in_vat_base), ZERO)
    vat_groups: dict[str, list] = defaultdict(lambda: [ZERO, None])
    total_ht = ZERO
    for pos, ln in enumerate(lines, start=1):
        qty, price, disc = D(ln.get("quantity", 1)), D(ln.get("unit_price", 0)), D(ln.get("discount_pct", 0))
        if qty == 0 or price < 0 or not (0 <= disc <= 100):
            raise HTTPException(400, f"Ligne {pos} : quantité, prix ou remise invalide")
        ht = q3(qty * price * (1 - disc / 100))
        vat_code = ln.get("vat_code") or "TVA19"
        vt = _active_tax(db, vat_code, inv.issue_date)
        if vt.kind != "TVA":
            raise HTTPException(400, f"Ligne {pos} : {vat_code} n'est pas un code TVA")
        inv.lines.append(InvoiceLine(position=pos, description=ln.get("description") or "-", quantity=qty, unit_price=price,
                                     discount_pct=disc, vat_code=vat_code, vat_rate=vt.rate,
                                     amount_ht=ht, vat_amount=q3(ht * (1 + in_base_pct / 100) * D(vt.rate) / 100)))
        total_ht += ht
        g = vat_groups[vat_code]
        g[0] += ht
        g[1] = vt
    other_total = ZERO
    for t in others:
        amt = q3(total_ht * D(t.rate) / 100) if t.rate is not None else q3(t.fixed_amount)
        inv.taxes.append(InvoiceTax(code=t.code, label=t.label, kind=t.kind, base=total_ht, rate=t.rate, amount=amt, account_code=t.account_code))
        other_total += amt
    total_vat = ZERO
    for code, (base_ht, vt) in sorted(vat_groups.items()):
        base = q3(base_ht * (1 + in_base_pct / 100))  # ex. FODEC inclus dans l'assiette TVA
        amt = q3(base * D(vt.rate) / 100)
        inv.taxes.append(InvoiceTax(code=code, label=vt.label, kind="TVA", base=base, rate=vt.rate, amount=amt, account_code=vt.account_code))
        total_vat += amt
    if apply_stamp:
        st = _active_tax(db, get_param(db, "invoice.stamp_duty_code", inv.issue_date), inv.issue_date)
        amt = q3(st.fixed_amount)
        inv.taxes.append(InvoiceTax(code=st.code, label=st.label, kind="TIMBRE", base=ZERO, rate=None, amount=amt, account_code=st.account_code))
        other_total += amt
    inv.total_ht = total_ht
    inv.total_vat = total_vat
    inv.total_other_taxes = other_total
    inv.total_ttc = total_ht + total_vat + other_total
    inv.balance = inv.total_ttc


def set_installments(inv: Invoice, schedule: list[dict] | None) -> None:
    inv.installments.clear()
    if not schedule:
        schedule = [{"due_date": inv.due_date, "amount": inv.total_ttc}]
    total = sum(q3(s["amount"]) for s in schedule)
    if total != inv.total_ttc:
        raise HTTPException(400, f"La somme des échéances ({total}) diffère du TTC ({inv.total_ttc})")
    for i, s in enumerate(sorted(schedule, key=lambda x: x["due_date"]), start=1):
        if q3(s["amount"]) <= 0:
            raise HTTPException(400, "Chaque échéance doit avoir un montant positif")
        due = s["due_date"] if isinstance(s["due_date"], dt.date) else dt.date.fromisoformat(str(s["due_date"]))
        if due < inv.issue_date:
            raise HTTPException(400, "Une échéance ne peut pas précéder la date de facture")
        inv.installments.append(Installment(seq=i, due_date=due, amount=q3(s["amount"]), amount_tnd=ZERO))
    inv.due_date = max(x.due_date for x in inv.installments)


def find_duplicates(db: Session, customer_id: int, issue_date: dt.date, total_ttc: Decimal,
                    external_ref: str | None = None, number: str | None = None, exclude_id: int | None = None) -> list[Invoice]:
    conds = [and_(Invoice.issue_date == issue_date, Invoice.total_ttc == total_ttc)]
    if external_ref:
        conds.append(Invoice.external_ref == external_ref)
    if number:
        conds.append(Invoice.number == number)
    q = select(Invoice).where(Invoice.customer_id == customer_id, or_(*conds))
    if exclude_id:
        q = q.where(Invoice.id != exclude_id)
    return list(db.execute(q).scalars())


def save_draft(db: Session, user: User, data: dict, inv: Invoice | None = None) -> Invoice:
    cust = db.get(Customer, data["customer_id"])
    if not cust:
        raise HTTPException(404, "Client introuvable")
    if cust.status == "ARCHIVE":
        raise HTTPException(409, "Client archivé")
    if inv is None:
        inv = Invoice(created_by=user.id, doc_type=data.get("doc_type", "FACTURE"), source=data.get("source", "SAISIE"))
        db.add(inv)
    elif inv.lifecycle != "BROUILLON":
        raise HTTPException(409, "Une pièce validée ne peut plus être modifiée : émettez un avoir")
    inv.customer_id = cust.id
    inv.customer = cust
    inv.issue_date = data["issue_date"]
    inv.due_date = data.get("due_date") or (inv.issue_date + dt.timedelta(days=cust.payment_terms_days))
    inv.currency = data.get("currency") or cust.currency or "TND"
    inv.exchange_rate = q6(data["exchange_rate"]) if data.get("exchange_rate") else get_rate(db, inv.currency, inv.issue_date)
    inv.external_ref = data.get("external_ref")
    inv.order_ref = data.get("order_ref")
    inv.notes = data.get("notes")
    inv.salesperson_id = data.get("salesperson_id") or cust.salesperson_id
    inv.related_invoice_id = data.get("related_invoice_id")
    if inv.doc_type == "AVOIR" and inv.related_invoice_id:
        rel = db.get(Invoice, inv.related_invoice_id)
        if not rel or rel.customer_id != cust.id or rel.doc_type != "FACTURE":
            raise HTTPException(400, "Facture d'origine de l'avoir invalide")
    default_stamp = inv.doc_type == "FACTURE" or get_param(db, "invoice.apply_stamp_on_credit_note")
    compute(db, inv, data.get("lines") or [], data.get("other_taxes") or [], default_stamp if data.get("apply_stamp") is None else data["apply_stamp"])
    set_installments(inv, data.get("installments") if inv.doc_type == "FACTURE" else None)
    db.flush()
    return inv


def validate(db: Session, user: User, inv: Invoice, force_over_limit: bool = False) -> dict:
    from .ledger import customer_exposure
    from ..permissions import has_permission
    if inv.lifecycle != "BROUILLON":
        raise HTTPException(409, "Pièce déjà validée")
    if inv.total_ttc <= 0:
        raise HTTPException(400, "Montant nul ou négatif")
    warnings = []
    cust = inv.customer
    if inv.doc_type == "FACTURE":
        exp = customer_exposure(db, cust.id)
        new_total = exp["open_tnd"] + q3(inv.total_ttc * inv.exchange_rate)
        if cust.credit_limit and new_total > cust.credit_limit:
            msg = f"Plafond de crédit dépassé : encours après facture {new_total} TND > plafond {cust.credit_limit} TND"
            if get_param(db, "credit.block_on_limit") and not (force_over_limit and has_permission(user.role, "customers.credit_limit")):
                raise HTTPException(409, msg + " (validation par le directeur financier requise)")
            warnings.append(msg)
        if cust.status == "BLOQUE":
            if not (force_over_limit and has_permission(user.role, "customers.credit_limit")):
                raise HTTPException(409, "Client bloqué : facturation soumise à l'accord du directeur financier")
            warnings.append("Client bloqué : validation forcée par le directeur financier")
    dups = find_duplicates(db, inv.customer_id, inv.issue_date, inv.total_ttc, inv.external_ref, exclude_id=inv.id)
    dups = [d for d in dups if d.lifecycle == "VALIDEE"]
    if dups:
        warnings.append("Doublon possible avec : " + ", ".join(d.number or str(d.id) for d in dups))
    if not inv.number:
        inv.number = next_number(db, inv.doc_type, inv.issue_date.year)
    rate = inv.exchange_rate
    inv.total_ttc_tnd = q3(inv.total_ttc * rate)
    inv.total_ht_tnd = q3(inv.total_ht * rate)
    # Contre-valeur TND des échéances : la dernière absorbe l'arrondi
    acc = ZERO
    for i, ins in enumerate(inv.installments):
        ins.amount_tnd = inv.total_ttc_tnd - acc if i == len(inv.installments) - 1 else q3(ins.amount * rate)
        acc += ins.amount_tnd
    inv.lifecycle = "VALIDEE"
    inv.validated_by = user.id
    inv.validated_at = now_utc()
    inv.balance = inv.total_ttc
    inv.paid_amount = ZERO
    db.flush()
    accounting.on_invoice_validated(db, inv)
    return {"warnings": warnings}


def installment_remaining(ins: Installment) -> Decimal:
    return ins.amount - ins.paid_amount


def recompute_invoice(db: Session, inv: Invoice) -> None:
    if inv.doc_type == "FACTURE":
        inv.paid_amount = sum((i.paid_amount for i in inv.installments), ZERO)
        inv.balance = inv.total_ttc - inv.paid_amount


def classify(db: Session, user: User, inv: Invoice, classification: str, reason: str) -> None:
    if inv.doc_type != "FACTURE" or inv.lifecycle != "VALIDEE":
        raise HTTPException(409, "Seule une facture validée peut être classée")
    if classification not in ("NORMALE", "LITIGIEUSE", "DOUTEUSE"):
        raise HTTPException(400, "Le passage en irrécouvrable se fait par une demande de passage en perte soumise à validation")
    if inv.classification == "IRRECOUVRABLE":
        raise HTTPException(409, "Facture déjà passée en perte")
    if not reason or len(reason.strip()) < 10:
        raise HTTPException(400, "Une justification détaillée (10 caractères minimum) est obligatoire")
    old = inv.classification
    if old == classification:
        return
    inv.classification = classification
    inv.classification_reason = reason
    inv.classified_at = now_utc()
    accounting.on_classification(db, inv, old, classification, dt.date.today())


def invoice_dict(inv: Invoice, as_of: dt.date | None = None, detail: bool = False) -> dict:
    st = settlement_status(inv, as_of)
    d = {
        "id": inv.id, "doc_type": inv.doc_type, "number": inv.number, "external_ref": inv.external_ref, "source": inv.source,
        "customer_id": inv.customer_id, "customer_code": inv.customer.code, "customer_name": inv.customer.legal_name,
        "issue_date": inv.issue_date, "due_date": inv.due_date, "currency": inv.currency, "exchange_rate": inv.exchange_rate,
        "total_ht": inv.total_ht, "total_vat": inv.total_vat, "total_other_taxes": inv.total_other_taxes,
        "total_ttc": inv.total_ttc, "total_ttc_tnd": inv.total_ttc_tnd, "paid_amount": inv.paid_amount, "balance": inv.balance,
        "balance_tnd": q3(inv.balance * inv.exchange_rate),
        "lifecycle": inv.lifecycle, "classification": inv.classification, "status": st, "status_label": SETTLEMENT_LABELS[st],
        "days_overdue": max(0, ((as_of or dt.date.today()) - inv.due_date).days) if inv.balance > 0 and inv.lifecycle == "VALIDEE" else 0,
        "related_invoice_id": inv.related_invoice_id, "order_ref": inv.order_ref,
    }
    if detail:
        d.update({
            "notes": inv.notes, "classification_reason": inv.classification_reason, "salesperson_id": inv.salesperson_id,
            "validated_at": inv.validated_at, "created_at": inv.created_at,
            "lines": [{"id": l.id, "position": l.position, "description": l.description, "quantity": l.quantity,
                       "unit_price": l.unit_price, "discount_pct": l.discount_pct, "vat_code": l.vat_code,
                       "vat_rate": l.vat_rate, "amount_ht": l.amount_ht, "vat_amount": l.vat_amount} for l in inv.lines],
            "taxes": [{"code": t.code, "label": t.label, "kind": t.kind, "base": t.base, "rate": t.rate, "amount": t.amount} for t in inv.taxes],
            "installments": [{"id": i.id, "seq": i.seq, "due_date": i.due_date, "amount": i.amount, "paid_amount": i.paid_amount,
                              "remaining": i.amount - i.paid_amount, "amount_tnd": i.amount_tnd} for i in inv.installments],
        })
    return d
