"""Grand livre auxiliaire, soldes, encours, balance âgée et contrôles de cohérence.

Deux vues indépendantes du même poste clients sont calculées :
1. le grand livre (mouvements débit/crédit datés) ;
2. les postes ouverts (restes dus des échéances – crédits non affectés).
À toute date, les deux soldes doivent être identiques : c'est le contrôle de
concordance permanente exigé par le cahier des charges.
"""
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..money import ZERO, q3
from ..models import Adjustment, Allocation, Customer, Installment, Invoice, Payment
from .params import get_param


# ------------------------------------------------------------------ grand livre
def movements(db: Session, customer_ids: list[int] | None = None, date_to: dt.date | None = None) -> list[dict]:
    date_to = date_to or dt.date.today()
    out: list[dict] = []
    cf = (lambda col: col.in_(customer_ids)) if customer_ids else (lambda col: True)
    for inv in db.execute(select(Invoice).where(Invoice.lifecycle == "VALIDEE", Invoice.issue_date <= date_to, cf(Invoice.customer_id))).scalars():
        fact = inv.doc_type == "FACTURE"
        out.append({"customer_id": inv.customer_id, "date": inv.issue_date, "type": "FACTURE" if fact else "AVOIR",
                    "piece": inv.number, "ref_id": inv.id, "label": f"{'Facture' if fact else 'Avoir'} {inv.number}",
                    "debit": inv.total_ttc_tnd if fact else ZERO, "credit": ZERO if fact else inv.total_ttc_tnd,
                    "due_date": inv.due_date if fact else None})
    for p in db.execute(select(Payment).where(Payment.receipt_date <= date_to, cf(Payment.customer_id))).scalars():
        out.append({"customer_id": p.customer_id, "date": p.receipt_date, "type": "REGLEMENT", "piece": p.number, "ref_id": p.id,
                    "label": f"Règlement {p.method.label} {p.reference or ''}".strip(), "debit": ZERO, "credit": p.amount_tnd})
        if p.rejected_date and p.rejected_date <= date_to:
            out.append({"customer_id": p.customer_id, "date": p.rejected_date, "type": "REJET", "piece": p.number, "ref_id": p.id,
                        "label": f"Rejet {p.method.label} {p.reference or ''} : {p.rejection_reason or ''}", "debit": p.amount_tnd, "credit": ZERO})
        if p.cancelled_date and p.cancelled_date <= date_to:
            out.append({"customer_id": p.customer_id, "date": p.cancelled_date, "type": "ANNULATION", "piece": p.number, "ref_id": p.id,
                        "label": f"Annulation règlement : {p.cancel_reason or ''}", "debit": p.amount_tnd, "credit": ZERO})
    for a in db.execute(select(Adjustment).where(Adjustment.date <= date_to, cf(Adjustment.customer_id))).scalars():
        out.append({"customer_id": a.customer_id, "date": a.date, "type": a.kind, "piece": a.number, "ref_id": a.id,
                    "label": f"{a.kind.replace('_', ' ').capitalize()} : {a.reason}", "debit": ZERO, "credit": a.amount_tnd})
    for al in db.execute(select(Allocation).where(Allocation.fx_difference_tnd != 0, cf(Allocation.customer_id))).scalars():
        if al.allocation_date <= date_to:
            fx = al.fx_difference_tnd
            out.append({"customer_id": al.customer_id, "date": al.allocation_date, "type": "CHANGE", "piece": al.invoice.number,
                        "ref_id": al.id, "label": "Différence de change", "debit": fx if fx > 0 else ZERO, "credit": -fx if fx < 0 else ZERO})
        if al.reversed_date and al.reversed_date <= date_to:
            fx = -al.fx_difference_tnd
            out.append({"customer_id": al.customer_id, "date": al.reversed_date, "type": "CHANGE", "piece": al.invoice.number,
                        "ref_id": al.id, "label": "Annulation différence de change", "debit": fx if fx > 0 else ZERO, "credit": -fx if fx < 0 else ZERO})
    order = {"FACTURE": 0, "AVOIR": 1, "REGLEMENT": 2, "CHANGE": 3}
    out.sort(key=lambda m: (m["customer_id"], m["date"], order.get(m["type"], 5), m["piece"] or ""))
    return out


def ledger(db: Session, customer_id: int, date_from: dt.date | None, date_to: dt.date | None) -> dict:
    movs = movements(db, [customer_id], date_to)
    opening = ZERO
    rows = []
    bal = ZERO
    for m in movs:
        if date_from and m["date"] < date_from:
            opening += m["debit"] - m["credit"]
            continue
        if not rows:
            bal = opening
        bal += m["debit"] - m["credit"]
        rows.append({**m, "balance": bal})
    total_d = sum((r["debit"] for r in rows), ZERO)
    total_c = sum((r["credit"] for r in rows), ZERO)
    return {"opening_balance": opening, "rows": rows, "total_debit": total_d, "total_credit": total_c,
            "closing_balance": opening + total_d - total_c}


def ledger_balances(db: Session, date_to: dt.date | None = None, date_from: dt.date | None = None) -> dict[int, dict]:
    """Balance auxiliaire : solde d'ouverture, mouvements et solde de clôture par client."""
    res: dict[int, dict] = defaultdict(lambda: {"opening": ZERO, "debit": ZERO, "credit": ZERO})
    for m in movements(db, None, date_to):
        r = res[m["customer_id"]]
        if date_from and m["date"] < date_from:
            r["opening"] += m["debit"] - m["credit"]
        else:
            r["debit"] += m["debit"]
            r["credit"] += m["credit"]
    for r in res.values():
        r["closing"] = r["opening"] + r["debit"] - r["credit"]
    return res


# ------------------------------------------------------------------ postes ouverts à date
def _alloc_active_at(as_of: dt.date):
    return and_(Allocation.allocation_date <= as_of, or_(Allocation.reversed_date.is_(None), Allocation.reversed_date > as_of))


def open_items(db: Session, as_of: dt.date | None = None, customer_ids: list[int] | None = None) -> list[dict]:
    """Reste dû de chaque échéance à la date d'arrêté (recalculé à partir des
    affectations datées : une balance âgée au 31/12 reste juste même si la
    facture a été réglée depuis)."""
    as_of = as_of or dt.date.today()
    paid = (select(Allocation.installment_id, func.sum(Allocation.amount).label("amt"), func.sum(Allocation.amount_tnd).label("tnd"))
            .where(_alloc_active_at(as_of)).group_by(Allocation.installment_id).subquery())
    q = (select(Installment, Invoice, func.coalesce(paid.c.amt, 0), func.coalesce(paid.c.tnd, 0))
         .join(Invoice, Installment.invoice_id == Invoice.id)
         .outerjoin(paid, paid.c.installment_id == Installment.id)
         .where(Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE", Invoice.issue_date <= as_of))
    if customer_ids:
        q = q.where(Invoice.customer_id.in_(customer_ids))
    out = []
    for ins, inv, amt, tnd in db.execute(q):
        rem = ins.amount - amt
        if rem <= 0:
            continue
        out.append({"installment_id": ins.id, "invoice_id": inv.id, "number": inv.number, "customer_id": inv.customer_id,
                    "issue_date": inv.issue_date, "due_date": ins.due_date, "currency": inv.currency,
                    "remaining": rem, "remaining_tnd": ins.amount_tnd - tnd, "amount_tnd": ins.amount_tnd,
                    "ht_ratio": (inv.total_ht / inv.total_ttc) if inv.total_ttc else Decimal(1),
                    "days_overdue": (as_of - ins.due_date).days, "classification": inv.classification,
                    "salesperson_id": inv.salesperson_id})
    return out


def unallocated_credits(db: Session, as_of: dt.date | None = None, customer_ids: list[int] | None = None) -> dict[int, Decimal]:
    """Crédits non affectés (avances, règlements non lettrés, avoirs non imputés) en TND à la date."""
    as_of = as_of or dt.date.today()
    res: dict[int, Decimal] = defaultdict(lambda: ZERO)

    def used(col, sid):
        return db.execute(select(func.coalesce(func.sum(Allocation.source_amount_tnd), 0)).where(col == sid, _alloc_active_at(as_of))).scalar()

    pq = select(Payment).where(Payment.receipt_date <= as_of,
                               or_(Payment.rejected_date.is_(None), Payment.rejected_date > as_of),
                               or_(Payment.cancelled_date.is_(None), Payment.cancelled_date > as_of))
    cq = select(Invoice).where(Invoice.doc_type == "AVOIR", Invoice.lifecycle == "VALIDEE", Invoice.issue_date <= as_of)
    aq = select(Adjustment).where(Adjustment.date <= as_of)
    if customer_ids:
        pq = pq.where(Payment.customer_id.in_(customer_ids))
        cq = cq.where(Invoice.customer_id.in_(customer_ids))
        aq = aq.where(Adjustment.customer_id.in_(customer_ids))
    for p in db.execute(pq).scalars():
        r = p.amount_tnd - used(Allocation.payment_id, p.id)
        if r:
            res[p.customer_id] += r
    for c in db.execute(cq).scalars():
        r = c.total_ttc_tnd - used(Allocation.credit_note_id, c.id)
        if r:
            res[c.customer_id] += r
    for a in db.execute(aq).scalars():
        r = a.amount_tnd - used(Allocation.adjustment_id, a.id)
        if r:
            res[a.customer_id] += r
    return res


def customer_exposure(db: Session, customer_id: int) -> dict:
    """Encours du client (vue risque du banquier) :
    - créances ouvertes (restes dus des factures) ;
    - effets et chèques reçus non encore encaissés (le risque subsiste jusqu'à l'encaissement : « sauf bonne fin »)."""
    open_tnd = db.execute(select(func.coalesce(func.sum(Installment.amount_tnd - Installment.paid_amount_tnd), 0))
                          .join(Invoice).where(Invoice.customer_id == customer_id, Invoice.lifecycle == "VALIDEE",
                                               Invoice.doc_type == "FACTURE")).scalar()
    pending = db.execute(select(func.coalesce(func.sum(Payment.amount_tnd), 0)).where(
        Payment.customer_id == customer_id, Payment.status.in_(["EN_PORTEFEUILLE", "REMIS"]))).scalar()
    overdue = db.execute(select(func.coalesce(func.sum(Installment.amount_tnd - Installment.paid_amount_tnd), 0))
                         .join(Invoice).where(Invoice.customer_id == customer_id, Invoice.lifecycle == "VALIDEE",
                                              Invoice.doc_type == "FACTURE", Installment.due_date < dt.date.today())).scalar()
    unalloc = unallocated_credits(db, None, [customer_id]).get(customer_id, ZERO)
    cust = db.get(Customer, customer_id)
    exposure = open_tnd + pending
    return {
        "open_tnd": q3(open_tnd), "overdue_tnd": q3(overdue), "pending_instruments_tnd": q3(pending),
        "unallocated_credits_tnd": q3(unalloc), "net_balance_tnd": q3(open_tnd - unalloc), "exposure_tnd": q3(exposure),
        "credit_limit": cust.credit_limit, "max_exposure": cust.max_exposure,
        "limit_usage_pct": float(open_tnd / cust.credit_limit * 100) if cust.credit_limit else None,
        "over_limit": bool(cust.credit_limit and open_tnd > cust.credit_limit),
        "over_exposure": bool(cust.max_exposure and exposure > cust.max_exposure),
        "available_credit": q3(cust.credit_limit - open_tnd) if cust.credit_limit else None,
    }


# ------------------------------------------------------------------ balance âgée
def bucket_defs(db: Session) -> list[tuple[str, int, int | None]]:
    out = [("NON_ECHU", -10 ** 9, 0)]
    for lo, hi in get_param(db, "aging.buckets"):
        out.append((f"{lo}-{hi}" if hi else f"{lo}+", lo, hi))
    return out


def bucket_of(days: int, defs) -> str:
    for code, lo, hi in defs:
        if days >= lo and (hi is None or days <= hi):
            return code
    return defs[-1][0]


def aging(db: Session, as_of: dt.date | None = None, customer_ids: list[int] | None = None,
          currency: str | None = None, group_by: str = "customer", filters: dict | None = None) -> dict:
    """Balance âgée au jour d'arrêté. Montants en TND (au cours historique de la
    facture) ou, si une devise est filtrée, dans la devise de facturation."""
    as_of = as_of or dt.date.today()
    defs = bucket_defs(db)
    filters = filters or {}
    custs = {c.id: c for c in db.execute(select(Customer)).scalars()}
    items = open_items(db, as_of, customer_ids)
    if currency:
        items = [i for i in items if i["currency"] == currency]
    unalloc = unallocated_credits(db, as_of, customer_ids) if not currency or currency == "TND" else {}

    def keep(cid):
        c = custs[cid]
        for k, attr in (("group_code", "group_code"), ("category_code", "category_code"), ("zone_code", "zone_code"),
                        ("sector_code", "sector_code"), ("risk_class", "risk_class"), ("salesperson_id", "salesperson_id")):
            if filters.get(k) not in (None, "") and str(getattr(c, attr)) != str(filters[k]):
                return False
        return True

    def key_of(it_or_cid):
        cid = it_or_cid if isinstance(it_or_cid, int) else it_or_cid["customer_id"]
        c = custs[cid]
        if group_by == "group":
            return c.group_code or "(sans groupe)"
        if group_by == "salesperson":
            return c.salesperson.full_name if c.salesperson else "(sans commercial)"
        if group_by == "risk":
            return c.risk_class or "(non évalué)"
        if group_by == "currency" and not isinstance(it_or_cid, int):
            return it_or_cid["currency"]
        return cid

    rows: dict = {}

    def row(k):
        if k not in rows:
            base = {"key": k, **{b[0]: ZERO for b in defs}, "total": ZERO, "unallocated": ZERO, "net": ZERO, "max_days": 0}
            if isinstance(k, int):
                c = custs[k]
                base.update({"customer_id": k, "code": c.code, "name": c.legal_name, "risk_class": c.risk_class,
                             "credit_limit": c.credit_limit})
            else:
                base.update({"name": k})
            rows[k] = base
        return rows[k]

    amount_field = "remaining" if currency and currency != "TND" else "remaining_tnd"
    for it in items:
        if not keep(it["customer_id"]):
            continue
        r = row(key_of(it))
        b = bucket_of(it["days_overdue"], defs)
        r[b] += it[amount_field]
        r["total"] += it[amount_field]
        r["max_days"] = max(r["max_days"], it["days_overdue"])
    if group_by != "currency":
        for cid, amt in unalloc.items():
            if keep(cid):
                row(key_of(cid))["unallocated"] += amt
    for r in rows.values():
        r["net"] = r["total"] - r["unallocated"]
    out = sorted(rows.values(), key=lambda r: -r["total"])
    totals = {b[0]: sum((r[b[0]] for r in out), ZERO) for b in defs}
    totals.update({k: sum((r[k] for r in out), ZERO) for k in ("total", "unallocated", "net")})
    pct = {b[0]: (float(totals[b[0]] / totals["total"] * 100) if totals["total"] else 0.0) for b in defs}
    return {"as_of": as_of, "buckets": [{"code": b[0], "label": "Non échu" if b[0] == "NON_ECHU" else (f"{b[1]} à {b[2]} j" if b[2] else f"> {b[1] - 1} j")} for b in defs],
            "rows": out, "totals": totals, "percentages": pct, "currency": currency or "TND"}


# ------------------------------------------------------------------ cohérence
def coherence_check(db: Session, as_of: dt.date | None = None) -> dict:
    """Contrôles de concordance : grand livre = postes ouverts, et caches = détail."""
    as_of = as_of or dt.date.today()
    anomalies = []
    led = ledger_balances(db, as_of)
    items = open_items(db, as_of)
    unalloc = unallocated_credits(db, as_of)
    oi: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for it in items:
        oi[it["customer_id"]] += it["remaining_tnd"]
    for cid in set(led) | set(oi) | set(unalloc):
        lb = led.get(cid, {}).get("closing", ZERO)
        ob = oi.get(cid, ZERO) - unalloc.get(cid, ZERO)
        if lb != ob:
            anomalies.append({"type": "GRAND_LIVRE_VS_POSTES_OUVERTS", "customer_id": cid, "ledger": lb, "open_items": ob, "diff": lb - ob})
    for inv in db.execute(select(Invoice).where(Invoice.lifecycle == "VALIDEE")).scalars():
        if inv.doc_type == "FACTURE":
            s = sum((i.amount for i in inv.installments), ZERO)
            if s != inv.total_ttc:
                anomalies.append({"type": "ECHEANCES_VS_TTC", "invoice": inv.number, "diff": s - inv.total_ttc})
            st = sum((i.amount_tnd for i in inv.installments), ZERO)
            if st != inv.total_ttc_tnd:
                anomalies.append({"type": "ECHEANCES_TND_VS_TTC_TND", "invoice": inv.number, "diff": st - inv.total_ttc_tnd})
            alloc = db.execute(select(func.coalesce(func.sum(Allocation.amount), 0)).where(Allocation.invoice_id == inv.id, Allocation.reversed_at.is_(None))).scalar()
            if alloc != inv.paid_amount or inv.balance != inv.total_ttc - inv.paid_amount:
                anomalies.append({"type": "FACTURE_REGLE_VS_AFFECTATIONS", "invoice": inv.number, "paid": inv.paid_amount, "allocations": alloc})
            for i in inv.installments:
                a = db.execute(select(func.coalesce(func.sum(Allocation.amount), 0)).where(Allocation.installment_id == i.id, Allocation.reversed_at.is_(None))).scalar()
                if a != i.paid_amount or i.paid_amount > i.amount or i.paid_amount < 0:
                    anomalies.append({"type": "ECHEANCE_INCOHERENTE", "invoice": inv.number, "seq": i.seq})
        else:
            alloc = db.execute(select(func.coalesce(func.sum(Allocation.amount), 0)).where(Allocation.credit_note_id == inv.id, Allocation.reversed_at.is_(None))).scalar()
            if alloc != inv.paid_amount or alloc > inv.total_ttc:
                anomalies.append({"type": "AVOIR_IMPUTATION_INCOHERENTE", "invoice": inv.number})
    for p in db.execute(select(Payment)).scalars():
        alloc = db.execute(select(func.coalesce(func.sum(Allocation.amount), 0)).where(Allocation.payment_id == p.id, Allocation.reversed_at.is_(None))).scalar()
        if alloc != p.allocated_amount or alloc > p.amount:
            anomalies.append({"type": "REGLEMENT_AFFECTATION_INCOHERENTE", "payment": p.number})
        if p.status in ("REJETE", "ANNULE") and alloc:
            anomalies.append({"type": "REGLEMENT_REJETE_ENCORE_AFFECTE", "payment": p.number})
    total_ledger = sum((v["closing"] for v in led.values()), ZERO)
    return {"as_of": as_of, "ok": not anomalies, "anomalies": anomalies, "total_ledger_tnd": total_ledger,
            "total_open_items_tnd": sum(oi.values(), ZERO), "total_unallocated_tnd": sum(unalloc.values(), ZERO)}
