"""Indicateurs du tableau de bord. Les formules sont documentées dans
docs/INDICATEURS.md et restituées avec chaque résultat (champ « formula »)."""
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..money import ZERO, q3
from ..models import Customer, Installment, Invoice, Payment
from .ledger import aging, open_items, unallocated_credits
from .params import get_param


def month_end(d: dt.date) -> dt.date:
    nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return nxt - dt.timedelta(days=1)


def sales_ttc(db: Session, start: dt.date, end: dt.date) -> Decimal:
    """Chiffre d'affaires TTC facturé (factures – avoirs validés) entre deux dates incluses."""
    f = db.execute(select(func.coalesce(func.sum(Invoice.total_ttc_tnd), 0)).where(
        Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE", Invoice.issue_date.between(start, end))).scalar()
    a = db.execute(select(func.coalesce(func.sum(Invoice.total_ttc_tnd), 0)).where(
        Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "AVOIR", Invoice.issue_date.between(start, end))).scalar()
    return f - a


def collections(db: Session, start: dt.date, end: dt.date) -> Decimal:
    """Encaissements de la période : règlements reçus, hors rejetés/annulés."""
    return db.execute(select(func.coalesce(func.sum(Payment.amount_tnd), 0)).where(
        Payment.receipt_date.between(start, end), Payment.status.not_in(["REJETE", "ANNULE"]))).scalar()


def receivables(db: Session, as_of: dt.date) -> dict:
    items = open_items(db, as_of)
    gross = sum((i["remaining_tnd"] for i in items), ZERO)
    overdue = sum((i["remaining_tnd"] for i in items if i["days_overdue"] > 0), ZERO)
    doubt = sum((i["remaining_tnd"] for i in items if i["classification"] == "DOUTEUSE"), ZERO)
    lit = sum((i["remaining_tnd"] for i in items if i["classification"] == "LITIGIEUSE"), ZERO)
    unal = sum(unallocated_credits(db, as_of).values(), ZERO)
    return {"gross": gross, "not_due": gross - overdue, "overdue": overdue, "doubtful": doubt, "disputed": lit,
            "unallocated": unal, "net": gross - unal, "items": items}


def dso(db: Session, as_of: dt.date, method: str | None = None, period_days: int | None = None) -> dict:
    method = method or get_param(db, "dso.method")
    period_days = int(period_days or get_param(db, "dso.period_days"))
    rec = receivables(db, as_of)["gross"]
    if method == "EPUISEMENT":
        # Méthode par épuisement (count-back) : on « consomme » les créances par
        # les ventes des mois précédents, du plus récent au plus ancien.
        remaining = rec
        days = 0
        end = as_of
        for _ in range(36):
            start = end.replace(day=1)
            s = sales_ttc(db, start, end)
            nb = (end - start).days + 1
            if s > 0 and remaining <= s:
                days += float(remaining / s) * nb
                remaining = ZERO
                break
            remaining -= max(s, ZERO)
            days += nb
            end = start - dt.timedelta(days=1)
        value = round(days, 1) if remaining == 0 else None
        formula = "Épuisement : créances TTC à la date, soustraites des ventes TTC mensuelles en remontant le temps ; DSO = nombre de jours de ventes nécessaires pour couvrir l'encours."
    else:
        start = as_of - dt.timedelta(days=period_days - 1)
        s = sales_ttc(db, start, as_of)
        value = round(float(rec / s * period_days), 1) if s > 0 else None
        formula = f"Comptable : créances clients TTC brutes à la date / CA TTC des {period_days} derniers jours × {period_days}."
    return {"value": value, "method": method, "period_days": period_days, "receivables": rec, "formula": formula}


def recovery_rate(db: Session, start: dt.date, end: dt.date) -> dict:
    """Taux de recouvrement = encaissements affectés à des échéances exigibles /
    montants exigibles (restes dus échus au début + échéances tombant dans la période)."""
    items_start = open_items(db, start - dt.timedelta(days=1))
    due_start = sum((i["remaining_tnd"] for i in items_start if i["due_date"] <= start - dt.timedelta(days=1)), ZERO)
    falling = db.execute(select(func.coalesce(func.sum(Installment.amount_tnd), 0)).join(Invoice).where(
        Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE", Installment.due_date.between(start, end))).scalar()
    exigible = due_start + falling
    coll = collections(db, start, end)
    definition = get_param(db, "kpi.recovery_rate_definition")
    return {"value": round(float(coll / exigible * 100), 1) if exigible else None, "collections": coll, "exigible": exigible,
            "definition": definition,
            "formula": "Encaissements de la période / (restes dus échus à l'ouverture + échéances de la période) × 100"}


def concentration(db: Session, as_of: dt.date, top_n: int | None = None) -> dict:
    top_n = int(top_n or get_param(db, "kpi.top_n"))
    per: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for i in open_items(db, as_of):
        per[i["customer_id"]] += i["remaining_tnd"]
    total = sum(per.values(), ZERO)
    ranked = sorted(per.items(), key=lambda kv: -kv[1])
    custs = {c.id: c for c in db.execute(select(Customer).where(Customer.id.in_(list(per) or [0]))).scalars()}
    top = [{"customer_id": cid, "code": custs[cid].code, "name": custs[cid].legal_name, "amount": amt,
            "share_pct": float(amt / total * 100) if total else 0, "risk_class": custs[cid].risk_class,
            "credit_limit": custs[cid].credit_limit} for cid, amt in ranked[:max(top_n, 10)]]
    share_top = sum((amt for _, amt in ranked[:top_n]), ZERO)
    hhi = sum(float(a / total) ** 2 for _, a in ranked) * 10000 if total else 0
    return {"top_n": top_n, "top_share_pct": float(share_top / total * 100) if total else 0, "hhi": round(hhi),
            "top": top, "total": total,
            "formula": f"Part des {top_n} premiers débiteurs dans le total des créances ; HHI = Σ(part²)×10 000 (>2 500 = forte concentration)."}


def monthly_trend(db: Session, as_of: dt.date, months: int = 12) -> list[dict]:
    out = []
    ends = []
    d = as_of
    for _ in range(months):
        ends.append(min(month_end(d), as_of))
        d = d.replace(day=1) - dt.timedelta(days=1)
    for e in reversed(ends):
        r = receivables(db, e)
        s = e.replace(day=1)
        out.append({"month": e.strftime("%Y-%m"), "date": e, "receivables": r["gross"], "overdue": r["overdue"],
                    "sales": sales_ttc(db, s, e), "collections": collections(db, s, e)})
    return out


def dashboard(db: Session, as_of: dt.date | None = None, period_start: dt.date | None = None) -> dict:
    as_of = as_of or dt.date.today()
    period_start = period_start or (as_of - dt.timedelta(days=29))  # période glissante de 30 jours par défaut
    r = receivables(db, as_of)
    ag = aging(db, as_of)
    conc = concentration(db, as_of)
    over = []
    for c in db.execute(select(Customer).where(Customer.credit_limit > 0)).scalars():
        amt = sum((i["remaining_tnd"] for i in r["items"] if i["customer_id"] == c.id), ZERO)
        if amt > c.credit_limit:
            over.append({"customer_id": c.id, "code": c.code, "name": c.legal_name, "outstanding": amt,
                         "credit_limit": c.credit_limit, "overrun": amt - c.credit_limit})
    pending = db.execute(select(func.coalesce(func.sum(Payment.amount_tnd), 0), func.count(Payment.id)).where(
        Payment.status.in_(["EN_PORTEFEUILLE", "REMIS"]))).one()
    risk_dist = dict(db.execute(select(Customer.risk_class, func.count(Customer.id)).group_by(Customer.risk_class)).all())
    coll = collections(db, period_start, as_of)
    return {
        "as_of": as_of, "period_start": period_start,
        "totals": {"receivables": r["gross"], "not_due": r["not_due"], "overdue": r["overdue"], "doubtful": r["doubtful"],
                   "disputed": r["disputed"], "unallocated_credits": r["unallocated"], "net_receivables": r["net"],
                   "collections_period": coll, "instruments_pending": pending[0], "instruments_pending_count": pending[1],
                   "sales_period": sales_ttc(db, period_start, as_of)},
        "dso": dso(db, as_of),
        "recovery_rate": recovery_rate(db, period_start, as_of),
        "unpaid_rate": {"value": round(float(r["overdue"] / r["gross"] * 100), 1) if r["gross"] else None,
                        "formula": "Créances échues impayées / total des créances brutes à la date × 100"},
        "concentration": conc,
        "aging": {"buckets": ag["buckets"], "totals": ag["totals"], "percentages": ag["percentages"]},
        "over_limit": sorted(over, key=lambda x: -x["overrun"]),
        "risk_distribution": {k or "NON_EVALUE": v for k, v in risk_dist.items()},
        "trend": monthly_trend(db, as_of, 12),
    }
