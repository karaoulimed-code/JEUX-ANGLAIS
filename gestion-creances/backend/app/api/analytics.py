"""Tableau de bord, balance âgée, IA explicable, états, comptabilité, alertes."""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import ApprovalRequest, Customer, DunningAction, Invoice, Installment, JournalEntry, Payment, ProvisionCampaign, User, now_utc
from ..permissions import has_permission
from ..security import get_current_user, require
from ..services import accounting, forecast, kpi, reports
from ..services.exports import to_csv, to_pdf, to_xlsx
from ..services.ledger import aging, coherence_check
from ..services.params import get_param
from .common import MEDIA, file_response, ip, out, scoped

router = APIRouter()


def _d(s: str | None):
    return dt.date.fromisoformat(s) if s else None


@router.get("/dashboard", tags=["Tableau de bord"])
def dashboard(as_of: dt.date | None = None, period_start: dt.date | None = None, user: User = Depends(require("dashboard.read")),
              db: Session = Depends(get_db)):
    if scoped(user):
        raise HTTPException(403, "Le tableau de bord global est réservé à la direction et à la comptabilité ; consultez vos clients")
    return out(kpi.dashboard(db, as_of, period_start))


@router.get("/aging", tags=["Balance âgée"])
def get_aging(as_of: dt.date | None = None, currency: str | None = None, group_by: str = "customer", customer_id: int | None = None,
              group_code: str | None = None, category_code: str | None = None, zone_code: str | None = None, sector_code: str | None = None,
              risk_class: str | None = None, salesperson_id: int | None = None,
              user: User = Depends(require("aging.read")), db: Session = Depends(get_db)):
    if scoped(user):
        salesperson_id = user.id
    return out(aging(db, as_of, [customer_id] if customer_id else None, currency, group_by,
                     {"group_code": group_code, "category_code": category_code, "zone_code": zone_code, "sector_code": sector_code,
                      "risk_class": risk_class, "salesperson_id": salesperson_id}))


@router.get("/coherence", tags=["Contrôles"])
def coherence(as_of: dt.date | None = None, user: User = Depends(require("accounting.read")), db: Session = Depends(get_db)):
    return out(coherence_check(db, as_of))


@router.get("/alerts", tags=["Tableau de bord"])
def alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = dt.date.today()
    res = []
    q = select(Customer).where(Customer.credit_limit > 0, Customer.status != "ARCHIVE")
    if scoped(user):
        q = q.where(Customer.salesperson_id == user.id)
    from ..services.ledger import customer_exposure
    pct = float(get_param(db, "credit.limit_alert_pct") or 90)
    for c in db.execute(q).scalars():
        e = customer_exposure(db, c.id)
        if e["over_limit"]:
            res.append({"level": "error", "type": "PLAFOND", "customer_id": c.id, "message": f"{c.legal_name} : plafond dépassé ({e['open_tnd']} / {c.credit_limit} TND)"})
        elif e["limit_usage_pct"] and e["limit_usage_pct"] >= pct:
            res.append({"level": "warning", "type": "PLAFOND", "customer_id": c.id, "message": f"{c.legal_name} : {e['limit_usage_pct']:.0f} % du plafond utilisé"})
    if has_permission(user.role, "payments.status"):
        n = db.execute(select(func.count(Payment.id)).where(Payment.status == "EN_PORTEFEUILLE", Payment.value_date <= today)).scalar()
        if n:
            res.append({"level": "warning", "type": "PORTEFEUILLE", "message": f"{n} chèque(s)/effet(s) arrivé(s) à date de remise en banque", "link": "/encaissements?status=EN_PORTEFEUILLE"})
    if has_permission(user.role, "dunning.write"):
        n = db.execute(select(func.count(DunningAction.id)).where(DunningAction.next_action_date <= today, DunningAction.next_action_date >= today - dt.timedelta(days=30))).scalar()
        if n:
            res.append({"level": "info", "type": "RELANCE", "message": f"{n} action(s) de recouvrement à effectuer", "link": "/recouvrement"})
    if has_permission(user.role, "approvals.decide"):
        n = db.execute(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "EN_ATTENTE", ApprovalRequest.requested_by != user.id)).scalar()
        if n:
            res.append({"level": "warning", "type": "APPROBATION", "message": f"{n} demande(s) en attente de votre validation", "link": "/approbations"})
    if has_permission(user.role, "provisions.validate"):
        n = db.execute(select(func.count(ProvisionCampaign.id)).where(ProvisionCampaign.status == "PROPOSEE", ProvisionCampaign.created_by != user.id)).scalar()
        if n:
            res.append({"level": "warning", "type": "PROVISION", "message": f"{n} campagne(s) de provisions à valider", "link": "/provisions"})
    if has_permission(user.role, "accounting.validate"):
        n = db.execute(select(func.count(JournalEntry.id)).where(JournalEntry.status == "PROPOSEE")).scalar()
        if n:
            res.append({"level": "info", "type": "ECRITURES", "message": f"{n} écriture(s) proposée(s) à valider", "link": "/comptabilite"})
    soon = db.execute(select(func.coalesce(func.sum(Installment.amount_tnd - Installment.paid_amount_tnd), 0), func.count(Installment.id))
                      .join(Invoice).where(Invoice.lifecycle == "VALIDEE", Installment.amount > Installment.paid_amount,
                                           Installment.due_date.between(today, today + dt.timedelta(days=7)))).one()
    if soon[1]:
        res.append({"level": "info", "type": "ECHEANCES", "message": f"{soon[1]} échéance(s) dans les 7 jours ({soon[0]} TND)", "link": "/recouvrement"})
    degraded = db.execute(select(Customer).where(Customer.risk_class == "CRITIQUE")).scalars().all()
    for c in degraded[:5]:
        if not scoped(user) or c.salesperson_id == user.id:
            res.append({"level": "error", "type": "RISQUE", "customer_id": c.id, "message": f"{c.legal_name} : risque critique (score {c.risk_score})"})
    return out(res)


# ------------------------------------------------------------------ IA explicable
@router.get("/ai/forecast", tags=["Aide à la décision"])
def ai_forecast(as_of: dt.date | None = None, user: User = Depends(require("forecast.read")), db: Session = Depends(get_db)):
    if scoped(user):
        raise HTTPException(403, "Prévision globale réservée à la direction financière")
    return out(forecast.cash_forecast(db, as_of))


@router.get("/ai/anomalies", tags=["Aide à la décision"])
def ai_anomalies(user: User = Depends(require("reports.read")), db: Session = Depends(get_db)):
    return out(forecast.anomalies(db))


@router.get("/ai/priorities", tags=["Aide à la décision"])
def ai_priorities(user: User = Depends(require("dunning.read")), db: Session = Depends(get_db)):
    res = forecast.priorities(db)
    if scoped(user):
        mine = {c.id for c in db.execute(select(Customer).where(Customer.salesperson_id == user.id)).scalars()}
        res = [r for r in res if r["customer_id"] in mine]
    return out(res)


@router.get("/ai/synthesis", tags=["Aide à la décision"])
def ai_synthesis(user: User = Depends(require("reports.read")), db: Session = Depends(get_db)):
    return out(forecast.synthesis(db))


# ------------------------------------------------------------------ états
@router.get("/reports", tags=["États"])
def catalog(user: User = Depends(require("reports.read"))):
    return out([{"code": k, "label": v[0]} for k, v in reports.CATALOG.items()])


@router.get("/reports/{name}", tags=["États"])
def report(name: str, request: Request, format: str = "json", user: User = Depends(require("reports.read")), db: Session = Depends(get_db)):
    p = dict(request.query_params)
    for k in ("date_from", "date_to"):
        if p.get(k):
            p[k] = _d(p[k])
    if name in ("provisions",) and not has_permission(user.role, "provisions.read"):
        raise HTTPException(403, "Droit insuffisant")
    r = reports.build(db, name, p)
    company = (get_param(db, "company") or {}).get("name", "")
    sub = r.get("subtitle") or " ".join(f"{k} : {v:%d/%m/%Y}" if isinstance(v, dt.date) else "" for k, v in p.items() if k in ("date_from", "date_to") and v)
    if format == "json":
        return out(r)
    audit.log(db, user, "REPORT_EXPORTED", "report", name, {"format": format, "params": {k: str(v) for k, v in p.items()}}, ip(request))
    db.commit()
    fname = f"{name}_{dt.date.today():%Y%m%d}.{format}"
    if format == "xlsx":
        return file_response(to_xlsx(r["title"], r["columns"], r["rows"], sub, r.get("totals")), fname, MEDIA["xlsx"])
    if format == "pdf":
        return file_response(to_pdf(r["title"], r["columns"], r["rows"], sub, r.get("totals"), company), fname, MEDIA["pdf"])
    if format == "csv":
        return file_response(to_csv(r["columns"], r["rows"], get_param(db, "export.csv_separator") or ";",
                                    bool(get_param(db, "export.decimal_comma"))), fname, MEDIA["csv"])
    raise HTTPException(400, "Format inconnu (json, xlsx, pdf, csv)")


# ------------------------------------------------------------------ comptabilité
@router.get("/accounting/entries", tags=["Comptabilité"])
def entries(status: str | None = None, journal: str | None = None, date_from: dt.date | None = None, date_to: dt.date | None = None,
            limit: int = 300, user: User = Depends(require("accounting.read")), db: Session = Depends(get_db)):
    q = select(JournalEntry).order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
    if status:
        q = q.where(JournalEntry.status == status)
    if journal:
        q = q.where(JournalEntry.journal == journal)
    if date_from:
        q = q.where(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.where(JournalEntry.entry_date <= date_to)
    res = []
    for e in db.execute(q.limit(min(limit, 3000))).scalars():
        res.append({"id": e.id, "number": e.number, "journal": e.journal, "entry_date": e.entry_date, "label": e.label, "status": e.status,
                    "source_type": e.source_type, "source_id": e.source_id, "export_batch": e.export_batch,
                    "total": sum((l.debit for l in e.lines), 0),
                    "lines": [{"account": l.account, "aux_account": l.aux_account, "label": l.label, "debit": l.debit, "credit": l.credit} for l in e.lines]})
    return out(res)


@router.post("/accounting/validate", tags=["Comptabilité"])
def validate_entries(body: dict, request: Request, user: User = Depends(require("accounting.validate")), db: Session = Depends(get_db)):
    ids = body.get("ids") or []
    n = 0
    for e in db.execute(select(JournalEntry).where(JournalEntry.id.in_(ids)).with_for_update()).scalars():
        accounting.validate_entry(db, e, user)
        n += 1
    audit.log(db, user, "ENTRIES_VALIDATED", "journal_entry", None, {"ids": ids}, ip(request))
    db.commit()
    return out({"validated": n})


@router.post("/accounting/export", tags=["Comptabilité"])
def export_entries(request: Request, body: dict | None = None, user: User = Depends(require("accounting.export")), db: Session = Depends(get_db)):
    """Exporte toutes les écritures validées non encore exportées (fichier CSV
    générique) ; elles passent au statut EXPORTEE et deviennent intangibles."""
    rows = list(db.execute(select(JournalEntry).where(JournalEntry.status == "VALIDEE").order_by(JournalEntry.entry_date, JournalEntry.id).with_for_update()).scalars())
    if not rows:
        raise HTTPException(409, "Aucune écriture validée à exporter")
    batch = f"EXP-{dt.datetime.now():%Y%m%d%H%M%S}"
    cols = [{"key": k, "label": k} for k in ("journal", "date", "piece", "compte", "compte_auxiliaire", "libelle", "debit", "credit")]
    data = []
    for e in rows:
        for l in e.lines:
            data.append({"journal": e.journal, "date": e.entry_date, "piece": e.number, "compte": l.account, "compte_auxiliaire": l.aux_account,
                         "libelle": l.label, "debit": l.debit, "credit": l.credit})
        e.status = "EXPORTEE"
        e.export_batch = batch
        e.exported_at = now_utc()
    audit.log(db, user, "ENTRIES_EXPORTED", "journal_entry", batch, {"count": len(rows)}, ip(request))
    content = to_csv(cols, data, get_param(db, "export.csv_separator") or ";", bool(get_param(db, "export.decimal_comma")))
    db.commit()
    return file_response(content, f"{batch}.csv", MEDIA["csv"])
