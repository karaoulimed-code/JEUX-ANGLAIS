"""Notation du risque client : score de 0 (aucun risque) à 100 (risque maximal).

Chaque critère rapporte des points proportionnels à sa pondération
(paramètre « risk.weights ») ; le détail est restitué ligne par ligne pour que
la note soit explicable et vérifiable, comme une grille de cotation bancaire.
"""
import datetime as dt
from decimal import Decimal
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..money import ZERO
from ..models import Allocation, Customer, Installment, Invoice, Payment, RiskSnapshot, now_utc
from .ledger import customer_exposure
from .params import get_param

CLASSES = ["FAIBLE", "MODERE", "ELEVE", "CRITIQUE"]
CLASS_LABELS = {"FAIBLE": "Risque faible", "MODERE": "Risque modéré", "ELEVE": "Risque élevé", "CRITIQUE": "Risque critique"}


def class_for(score: float, th: dict) -> str:
    if score >= th["CRITIQUE"]:
        return "CRITIQUE"
    if score >= th["ELEVE"]:
        return "ELEVE"
    if score >= th["MODERE"]:
        return "MODERE"
    return "FAIBLE"


def payment_delays(db: Session, customer_id: int | None, since: dt.date) -> list[tuple[dt.date, int, Decimal]]:
    """Retards observés (date de lettrage par un règlement – date d'échéance), pondérables par montant."""
    q = (select(Allocation.allocation_date, Installment.due_date, Allocation.amount_tnd, Allocation.customer_id)
         .join(Installment, Allocation.installment_id == Installment.id)
         .where(Allocation.payment_id.is_not(None), Allocation.reversed_at.is_(None), Allocation.allocation_date >= since))
    if customer_id:
        q = q.where(Allocation.customer_id == customer_id)
    return [(d, (d - due).days, amt) for d, due, amt, _ in db.execute(q)]


def _wavg(rows):
    tot = sum(float(a) for _, _, a in rows)
    return sum(max(0, d) * float(a) for _, d, a in rows) / tot if tot else 0.0


def compute(db: Session, customer: Customer, as_of: dt.date | None = None, save: bool = True) -> dict:
    as_of = as_of or dt.date.today()
    w = get_param(db, "risk.weights")
    th = get_param(db, "risk.thresholds")
    grace = int(get_param(db, "risk.late_grace_days") or 0)
    exp = customer_exposure(db, customer.id)
    outstanding = float(exp["open_tnd"])
    overdue = float(exp["overdue_tnd"])
    # ancienneté de la plus vieille échéance impayée
    oldest = db.execute(select(func.min(Installment.due_date)).join(Invoice).where(
        Invoice.customer_id == customer.id, Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE",
        Installment.amount > Installment.paid_amount, Installment.due_date < as_of)).scalar()
    max_days = (as_of - oldest).days if oldest else 0
    hist = payment_delays(db, customer.id, as_of - dt.timedelta(days=365))
    avg_delay = _wavg(hist)
    late_freq = (sum(1 for _, d, _ in hist if d > grace) / len(hist)) if hist else 0.0
    incidents = db.execute(select(func.count(Payment.id)).where(
        Payment.customer_id == customer.id, Payment.status == "REJETE", Payment.rejected_date >= as_of - dt.timedelta(days=365))).scalar()
    usage = (outstanding / float(customer.credit_limit)) if customer.credit_limit else None
    total_all = float(db.execute(select(func.coalesce(func.sum(Installment.amount_tnd - Installment.paid_amount_tnd), 0)).join(Invoice)
                                 .where(Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE")).scalar() or 0)
    share = outstanding / total_all if total_all else 0.0
    recent = [h for h in hist if h[0] >= as_of - dt.timedelta(days=90)]
    older = [h for h in hist if h[0] < as_of - dt.timedelta(days=90)]
    trend = (_wavg(recent) - _wavg(older)) if recent and older else 0.0

    def lin(x, full):
        return max(0.0, min(1.0, x / full)) if full else 0.0

    criteria = [
        ("overdue_ratio", "Part des créances échues", f"{(overdue / outstanding * 100 if outstanding else 0):.1f} %",
         lin(overdue / outstanding if outstanding else 0, 1), "100 % d'échu = maximum"),
        ("max_days_overdue", "Ancienneté du plus vieil impayé", f"{max_days} jours", lin(max_days, 180), "180 jours = maximum"),
        ("avg_delay", "Retard moyen de paiement (12 mois, pondéré)", f"{avg_delay:.0f} jours", lin(avg_delay, 90), "90 jours = maximum"),
        ("late_frequency", "Fréquence des paiements en retard", f"{late_freq * 100:.0f} % des règlements", late_freq,
         f"retard > {grace} j de tolérance"),
        ("incidents", "Incidents de paiement (rejets, 12 mois)", f"{incidents}", lin(incidents, 3), "3 incidents = maximum"),
        ("limit_overrun", "Utilisation du plafond de crédit", f"{usage * 100:.0f} %" if usage is not None else "aucun plafond",
         (max(0.0, min(1.0, (usage - 0.8) / 0.4)) if usage is not None else (0.5 if outstanding > 0 else 0.0)),
         "0 point jusqu'à 80 %, maximum à 120 % ; sans plafond défini = 50 %"),
        ("concentration", "Poids dans le total des créances", f"{share * 100:.1f} %", lin(share, 0.25), "25 % du portefeuille = maximum"),
        ("trend", "Dégradation récente (3 derniers mois vs antérieur)", f"{trend:+.0f} jours", lin(trend, 30), "+30 jours = maximum"),
    ]
    details = []
    score = 0.0
    for key, label, value, ratio, rule in criteria:
        pts = round(float(w.get(key, 0)) * ratio, 1)
        score += pts
        details.append({"criterion": key, "label": label, "value": value, "points": pts, "max_points": w.get(key, 0), "rule": rule})
    flags = []
    disputed = db.execute(select(func.count(Invoice.id)).where(Invoice.customer_id == customer.id, Invoice.balance > 0,
                                                              Invoice.classification.in_(["DOUTEUSE", "LITIGIEUSE"]))).scalar()
    score = round(min(100.0, score))
    rc = class_for(score, th)
    if customer.in_litigation or disputed:
        flags.append("Client en contentieux ou créances douteuses/litigieuses : classe minimale « Risque élevé »")
        if CLASSES.index(rc) < CLASSES.index("ELEVE"):
            rc = "ELEVE"
    if exp["over_limit"]:
        flags.append("Plafond de crédit dépassé")
    if exp["over_exposure"]:
        flags.append("Encours maximal (créances + effets/chèques en circulation) dépassé")
    previous = customer.risk_class
    degraded = previous is not None and CLASSES.index(rc) > CLASSES.index(previous)
    if degraded:
        flags.append(f"Dégradation : {CLASS_LABELS[previous]} → {CLASS_LABELS[rc]}")
    result = {"customer_id": customer.id, "as_of": as_of, "score": int(score), "risk_class": rc, "risk_label": CLASS_LABELS[rc],
              "previous_class": previous, "degraded": degraded, "criteria": details, "flags": flags,
              "metrics": {"outstanding_tnd": outstanding, "overdue_tnd": overdue, "max_days_overdue": max_days,
                          "avg_delay_days": round(avg_delay, 1), "late_frequency": round(late_freq, 3), "incidents_12m": incidents,
                          "limit_usage": usage, "portfolio_share": share, "trend_days": round(trend, 1), "observations": len(hist)}}
    if save:
        customer.risk_score = int(score)
        customer.risk_class = rc
        customer.risk_computed_at = now_utc()
        db.add(RiskSnapshot(customer_id=customer.id, as_of=as_of, score=int(score), risk_class=rc,
                            details={"criteria": details, "flags": flags, "metrics": result["metrics"]}))
    return result


def compute_all(db: Session, as_of: dt.date | None = None) -> list[dict]:
    out = []
    for c in db.execute(select(Customer).where(Customer.status != "ARCHIVE")).scalars():
        out.append(compute(db, c, as_of))
    return out
