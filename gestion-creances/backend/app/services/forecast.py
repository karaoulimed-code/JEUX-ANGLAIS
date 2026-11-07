"""Module d'aide à la décision (« IA » explicable, niveau 1 : statistique).

Toutes les prévisions reposent sur l'historique réel des règlements du client,
sans boîte noire : chaque date prévue est accompagnée de la règle appliquée et
du nombre d'observations. Une interface (AIProvider) permet de brancher plus
tard un modèle de langage pour la rédaction ; ses propositions restent soumises
à validation humaine.
"""
import datetime as dt
from collections import defaultdict
from statistics import mean, median, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import ZERO
from ..models import Customer, Invoice, Payment
from .ledger import open_items, unallocated_credits
from .params import get_param
from .risk import payment_delays

MIN_OBS = 3


def behaviour(db: Session, as_of: dt.date) -> tuple[dict[int, dict], dict]:
    rows = []
    from ..models import Allocation, Installment
    res = db.execute(select(Allocation.customer_id, Allocation.allocation_date, Installment.due_date, Allocation.amount_tnd)
                     .join(Installment, Allocation.installment_id == Installment.id)
                     .where(Allocation.payment_id.is_not(None), Allocation.reversed_at.is_(None),
                            Allocation.allocation_date >= as_of - dt.timedelta(days=730)))
    per: dict[int, list[int]] = defaultdict(list)
    for cid, d, due, amt in res:
        per[cid].append((d - due).days)
        rows.append((d - due).days)
    stats = {cid: {"n": len(v), "median": median(v), "mean": mean(v), "std": pstdev(v) if len(v) > 1 else 0.0} for cid, v in per.items()}
    glob = {"n": len(rows), "median": median(rows) if rows else 0, "mean": mean(rows) if rows else 0,
            "std": pstdev(rows) if len(rows) > 1 else 0.0}
    return stats, glob


def predict(db: Session, as_of: dt.date | None = None) -> list[dict]:
    """Date probable d'encaissement de chaque échéance ouverte."""
    as_of = as_of or dt.date.today()
    stats, glob = behaviour(db, as_of)
    out = []
    for it in open_items(db, as_of):
        cid = it["customer_id"]
        if it["classification"] in ("DOUTEUSE", "LITIGIEUSE") or it["days_overdue"] > 180:
            out.append({**it, "predicted_date": None, "confidence": "EXCLU",
                        "rule": "Créance douteuse, litigieuse ou de plus de 180 jours : encaissement non prévisible, exclue de la prévision"})
            continue
        s = stats.get(cid)
        if s and s["n"] >= MIN_OBS:
            delay = s["median"]
            conf = "BONNE" if s["std"] <= 15 and s["n"] >= 6 else "MOYENNE"
            rule = f"Échéance + retard médian du client ({delay:.0f} j sur {s['n']} règlements)"
        elif glob["n"] >= MIN_OBS:
            delay = glob["median"]
            conf = "FAIBLE"
            rule = f"Historique client insuffisant : retard médian de l'ensemble des clients ({delay:.0f} j)"
        else:
            delay = 0
            conf = "FAIBLE"
            rule = "Aucun historique : date d'échéance contractuelle"
        pdate = it["due_date"] + dt.timedelta(days=round(delay))
        if pdate < as_of:
            pdate = as_of + dt.timedelta(days=7)
            rule += " ; date dépassée : reportée à J+7"
        out.append({**it, "predicted_date": pdate, "confidence": conf, "rule": rule})
    return out


def cash_forecast(db: Session, as_of: dt.date | None = None, weeks: int = 13) -> dict:
    as_of = as_of or dt.date.today()
    preds = predict(db, as_of)
    start = as_of - dt.timedelta(days=as_of.weekday())
    buckets = [{"week_start": start + dt.timedelta(weeks=i), "invoices": ZERO, "instruments": ZERO, "contractual": ZERO} for i in range(weeks)]
    horizon_end = start + dt.timedelta(weeks=weeks)

    def idx(d):
        if d is None or d >= horizon_end:
            return None
        return max(0, (d - start).days // 7)

    beyond = ZERO
    excluded = ZERO
    for p in preds:
        if p["predicted_date"] is None:
            excluded += p["remaining_tnd"]
            continue
        i = idx(p["predicted_date"])
        if i is None:
            beyond += p["remaining_tnd"]
        else:
            buckets[i]["invoices"] += p["remaining_tnd"]
        j = idx(max(p["due_date"], as_of))
        if j is not None:
            buckets[j]["contractual"] += p["remaining_tnd"]
    for pay in db.execute(select(Payment).where(Payment.status.in_(["EN_PORTEFEUILLE", "REMIS"]))).scalars():
        i = idx(max(pay.value_date or as_of, as_of))
        if i is not None:
            buckets[i]["instruments"] += pay.amount_tnd
    cum = ZERO
    for b in buckets:
        b["total"] = b["invoices"] + b["instruments"]
        cum += b["total"]
        b["cumulative"] = cum
        b["week_end"] = b["week_start"] + dt.timedelta(days=6)
    monthly: dict[str, dict] = defaultdict(lambda: {"invoices": ZERO, "instruments": ZERO})
    for p in preds:
        if p["predicted_date"]:
            monthly[p["predicted_date"].strftime("%Y-%m")]["invoices"] += p["remaining_tnd"]
    for pay in db.execute(select(Payment).where(Payment.status.in_(["EN_PORTEFEUILLE", "REMIS"]))).scalars():
        monthly[max(pay.value_date or as_of, as_of).strftime("%Y-%m")]["instruments"] += pay.amount_tnd
    months = [{"month": k, **v, "total": v["invoices"] + v["instruments"]} for k, v in sorted(monthly.items())][:6]
    return {"as_of": as_of, "weeks": buckets, "months": months, "beyond_horizon": beyond, "excluded_uncertain": excluded,
            "details": preds,
            "method": "Factures : date d'échéance + retard médian historique du client (24 mois) ; chèques et effets en portefeuille : "
                      "date de valeur prévue. Les créances douteuses/litigieuses ou de plus de 180 jours sont exclues."}


def anomalies(db: Session, as_of: dt.date | None = None) -> list[dict]:
    as_of = as_of or dt.date.today()
    out = []
    # 1. Doublons potentiels de factures
    seen = defaultdict(list)
    for inv in db.execute(select(Invoice).where(Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE")).scalars():
        seen[(inv.customer_id, inv.issue_date, inv.total_ttc)].append(inv)
    for (cid, d, amt), invs in seen.items():
        if len(invs) > 1:
            out.append({"type": "DOUBLON_FACTURE", "severity": "ELEVEE", "customer_id": cid,
                        "message": f"{len(invs)} factures du même client, même date ({d:%d/%m/%Y}) et même montant ({amt}) : "
                                   + ", ".join(i.number for i in invs)})
    # 2. Règlements inhabituels (montant > moyenne + 3 écarts-types du client)
    per = defaultdict(list)
    pays = list(db.execute(select(Payment).where(Payment.status != "ANNULE")).scalars())
    for p in pays:
        per[p.customer_id].append(float(p.amount_tnd))
    for p in pays:
        v = per[p.customer_id]
        if len(v) >= 5:
            m, s = mean(v), pstdev(v)
            if s and float(p.amount_tnd) > m + 3 * s and p.receipt_date >= as_of - dt.timedelta(days=90):
                out.append({"type": "REGLEMENT_INHABITUEL", "severity": "MOYENNE", "customer_id": p.customer_id,
                            "message": f"Règlement {p.number} de {p.amount_tnd} TND très supérieur aux habitudes du client (moyenne {m:.3f})"})
    # 3. Changement de comportement de paiement
    stats, _ = behaviour(db, as_of - dt.timedelta(days=90))
    recent = defaultdict(list)
    from ..models import Allocation, Installment
    for cid, d, due in db.execute(select(Allocation.customer_id, Allocation.allocation_date, Installment.due_date)
                                  .join(Installment, Allocation.installment_id == Installment.id)
                                  .where(Allocation.payment_id.is_not(None), Allocation.reversed_at.is_(None),
                                         Allocation.allocation_date > as_of - dt.timedelta(days=90))):
        recent[cid].append((d - due).days)
    for cid, v in recent.items():
        s = stats.get(cid)
        if s and s["n"] >= MIN_OBS and len(v) >= 2 and mean(v) > s["mean"] + max(15, 2 * s["std"]):
            out.append({"type": "DEGRADATION_COMPORTEMENT", "severity": "ELEVEE", "customer_id": cid,
                        "message": f"Retard moyen récent {mean(v):.0f} j contre {s['mean']:.0f} j historiquement"})
    # 4. Règlements non affectés depuis plus de 30 jours
    for p in pays:
        if p.status not in ("REJETE", "ANNULE") and p.amount > p.allocated_amount and p.receipt_date < as_of - dt.timedelta(days=30):
            out.append({"type": "REGLEMENT_NON_AFFECTE", "severity": "MOYENNE", "customer_id": p.customer_id,
                        "message": f"Règlement {p.number} : {p.amount - p.allocated_amount} non affectés depuis le {p.receipt_date:%d/%m/%Y}"})
    custs = {c.id: c for c in db.execute(select(Customer)).scalars()}
    for a in out:
        c = custs.get(a["customer_id"])
        a["customer_name"] = c.legal_name if c else None
        a["customer_code"] = c.code if c else None
    return out


def priorities(db: Session, as_of: dt.date | None = None, limit: int = 30) -> list[dict]:
    """Priorités de recouvrement : montant échu × (1 + score de risque/100) × facteur d'ancienneté."""
    as_of = as_of or dt.date.today()
    per = defaultdict(lambda: {"amount": ZERO, "max_days": 0})
    for it in open_items(db, as_of):
        if it["days_overdue"] > 0 and it["classification"] != "IRRECOUVRABLE":
            r = per[it["customer_id"]]
            r["amount"] += it["remaining_tnd"]
            r["max_days"] = max(r["max_days"], it["days_overdue"])
    custs = {c.id: c for c in db.execute(select(Customer).where(Customer.id.in_(list(per) or [0]))).scalars()}
    out = []
    for cid, r in per.items():
        c = custs[cid]
        risk = (c.risk_score or 0) / 100
        age = 1 + min(r["max_days"], 180) / 180
        score = float(r["amount"]) * (1 + risk) * age
        reasons = [f"{r['amount']} TND échus", f"plus ancien retard {r['max_days']} j"]
        if c.risk_class:
            reasons.append(f"risque {c.risk_class.lower()} (score {c.risk_score})")
        out.append({"customer_id": cid, "code": c.code, "name": c.legal_name, "amount_overdue": r["amount"],
                    "max_days": r["max_days"], "priority_score": round(score), "reasons": reasons})
    out.sort(key=lambda x: -x["priority_score"])
    return out[:limit]


def synthesis(db: Session, as_of: dt.date | None = None) -> dict:
    """Synthèse financière rédigée automatiquement à partir des indicateurs (sans LLM)."""
    from .kpi import dashboard
    d = dashboard(db, as_of)
    t = d["totals"]

    def f(v):
        return f"{v:,.3f}".replace(",", " ").replace(".", ",") + " TND"
    lines = [
        f"Au {d['as_of']:%d/%m/%Y}, l'encours clients brut s'élève à {f(t['receivables'])}, dont {f(t['overdue'])} échus "
        f"({d['unpaid_rate']['value'] or 0} % de l'encours).",
        f"Le DSO ({d['dso']['method'].lower()}) ressort à {d['dso']['value'] if d['dso']['value'] is not None else 'n.d.'} jours.",
        f"Encaissements depuis le {d['period_start']:%d/%m/%Y} : {f(t['collections_period'])} ; taux de recouvrement "
        f"{d['recovery_rate']['value'] if d['recovery_rate']['value'] is not None else 'n.d.'} %.",
        f"Les {d['concentration']['top_n']} premiers débiteurs représentent {d['concentration']['top_share_pct']:.1f} % de l'encours.",
    ]
    if t["doubtful"] or t["disputed"]:
        lines.append(f"Créances douteuses : {f(t['doubtful'])} ; litigieuses : {f(t['disputed'])}.")
    if d["over_limit"]:
        lines.append(f"{len(d['over_limit'])} client(s) dépassent leur plafond de crédit, dont "
                     f"{d['over_limit'][0]['name']} (+{f(d['over_limit'][0]['overrun'])}).")
    if t["instruments_pending"]:
        lines.append(f"{t['instruments_pending_count']} chèque(s)/effet(s) en portefeuille pour {f(t['instruments_pending'])} restent à encaisser.")
    import re as _re
    text = _re.sub(r"(\d)\.(\d)", r"\1,\2", "\n".join(lines))  # virgule décimale française
    return {"as_of": d["as_of"], "text": text, "generated_by": "règles déterministes (aucun modèle externe)"}


class AIProvider:
    """Point d'extension pour un modèle de langage (rédaction de relances,
    synthèses enrichies). Désactivé par défaut : aucune donnée client ne quitte
    le serveur sans activation explicite par l'administrateur."""

    enabled = False

    def draft_letter(self, context: dict) -> str:  # pragma: no cover - extension future
        raise NotImplementedError
