"""Créances douteuses et provisions.

Deux référentiels, strictement séparés :

* NCT (comptes sociaux tunisiens) : provision individuelle, à hauteur de la
  perte probable (principe de prudence). La grille de taux par ancienneté n'est
  qu'une AIDE à l'estimation (politique interne paramétrable) : le taux retenu
  doit être justifié dossier par dossier. La déductibilité fiscale (article 48
  du Code de l'IRPP et de l'IS, plafond de 50 % du bénéfice imposable et
  conditions de forme) est suivie séparément et doit être validée par
  l'expert-comptable.

* IFRS 9 (approche simplifiée, matrice de provisionnement) : pertes de crédit
  attendues sur toute la durée de vie, appliquées à l'ensemble des créances
  selon leur ancienneté. Usage : reporting IFRS / groupe, pas les comptes
  sociaux tunisiens, sauf décision contraire documentée.

Une campagne est proposée par un utilisateur et validée par un autre
(séparation des fonctions) ; seule une campagne validée génère des écritures.
"""
import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import ZERO, D, q3
from ..models import Invoice, Provision, ProvisionCampaign, User, now_utc
from . import accounting
from .ledger import bucket_defs, bucket_of, open_items
from .params import get_param

FISCAL_NOTE = ("Déductibilité à vérifier par l'expert-comptable : article 48 du Code de l'IRPP et de l'IS "
               "(provisions pour créances douteuses déductibles dans la limite de 50 % du bénéfice imposable, "
               "sous réserve des conditions prévues par le texte en vigueur, notamment l'engagement d'une action en justice).")


def current_provisions(db: Session, method: str, as_of: dt.date | None = None) -> dict[int, Decimal]:
    """Dernière provision validée par facture pour un référentiel."""
    q = (select(Provision, ProvisionCampaign).join(ProvisionCampaign)
         .where(ProvisionCampaign.status == "VALIDEE", ProvisionCampaign.method == method)
         .order_by(ProvisionCampaign.as_of, ProvisionCampaign.id))
    if as_of:
        q = q.where(ProvisionCampaign.as_of <= as_of)
    out: dict[int, Decimal] = {}
    last_campaign: dict[int, int] = {}
    for p, c in db.execute(q):
        out[p.invoice_id] = p.amount_tnd
        last_campaign[p.invoice_id] = c.id
    return out


def suggested_nct_rate(db: Session, days: int, classification: str) -> Decimal:
    rate = ZERO
    for g in get_param(db, "provision.nct.grid"):
        if days >= g["min_days"] and (g["max_days"] is None or days <= g["max_days"]):
            rate = D(g["rate"])
    mins = get_param(db, "provision.nct.classification_min_rate") or {}
    return max(rate, D(mins.get(classification, 0)))


def propose(db: Session, user: User, as_of: dt.date, method: str, notes: str | None = None) -> ProvisionCampaign:
    if method not in ("NCT", "IFRS9"):
        raise HTTPException(400, "Méthode inconnue (NCT ou IFRS9)")
    if db.execute(select(ProvisionCampaign).where(ProvisionCampaign.method == method, ProvisionCampaign.status == "PROPOSEE")).first():
        raise HTTPException(409, "Une campagne de ce référentiel est déjà en attente de validation")
    prev = current_provisions(db, method)
    c = ProvisionCampaign(as_of=as_of, method=method, notes=notes, created_by=user.id)
    db.add(c)
    defs = bucket_defs(db)
    seen = set()
    min_days = int(get_param(db, "provision.nct.min_days") or 0)
    base_mode = get_param(db, "provision.nct.base" if method == "NCT" else "provision.ifrs9.base")
    matrix = get_param(db, "provision.ifrs9.matrix") or {}
    # Regroupement des échéances par facture
    per_inv: dict[int, dict] = {}
    for it in open_items(db, as_of):
        if it["classification"] == "IRRECOUVRABLE":
            continue
        r = per_inv.setdefault(it["invoice_id"], {"outstanding": ZERO, "base": ZERO, "days": -10**6, "cls": it["classification"],
                                                  "customer_id": it["customer_id"], "ifrs_amount": ZERO})
        r["outstanding"] += it["remaining_tnd"]
        base = q3(it["remaining_tnd"] * it["ht_ratio"]) if base_mode == "HT" else it["remaining_tnd"]
        r["base"] += base
        r["days"] = max(r["days"], it["days_overdue"])
        if method == "IFRS9":
            rate = D(matrix.get(bucket_of(it["days_overdue"], defs), 0))
            r["ifrs_amount"] += q3(base * rate / 100)
    for iid, r in per_inv.items():
        if method == "NCT":
            if r["cls"] not in ("DOUTEUSE", "LITIGIEUSE") and r["days"] < min_days and not prev.get(iid):
                continue
            rate = suggested_nct_rate(db, max(0, r["days"]), r["cls"])
            amount = q3(r["base"] * rate / 100)
        else:
            amount = r["ifrs_amount"]
            rate = (amount / r["base"] * 100).quantize(Decimal("0.0001")) if r["base"] else ZERO
        if amount == 0 and not prev.get(iid):
            continue
        seen.add(iid)
        c.lines.append(Provision(invoice_id=iid, customer_id=r["customer_id"], method=method,
                                 bucket=bucket_of(r["days"], defs), days_overdue=max(0, r["days"]), outstanding_tnd=r["outstanding"],
                                 base_tnd=r["base"], rate=rate, suggested_rate=rate, amount_tnd=amount,
                                 previous_amount_tnd=prev.get(iid, ZERO), movement_tnd=amount - prev.get(iid, ZERO),
                                 fiscal_note=FISCAL_NOTE if method == "NCT" else None))
    # Factures provisionnées mais désormais soldées ou passées en perte : reprise totale
    for iid, amt in prev.items():
        if iid in seen or amt == 0:
            continue
        inv = db.get(Invoice, iid)
        c.lines.append(Provision(invoice_id=iid, customer_id=inv.customer_id, method=method, bucket=None, days_overdue=0,
                                 outstanding_tnd=ZERO, base_tnd=ZERO, rate=ZERO, suggested_rate=ZERO, amount_tnd=ZERO,
                                 previous_amount_tnd=amt, movement_tnd=-amt, justification="Reprise : créance soldée ou passée en perte"))
    c.total_amount_tnd = sum((ln.amount_tnd for ln in c.lines), ZERO)
    db.flush()
    return c


def update_line(db: Session, line: Provision, rate, justification: str | None, fiscal_deductible: bool | None) -> None:
    if line.campaign.status != "PROPOSEE":
        raise HTTPException(409, "Campagne déjà décidée")
    rate = D(rate)
    if not (0 <= rate <= 100):
        raise HTTPException(400, "Taux entre 0 et 100 %")
    line.rate = rate
    line.amount_tnd = q3(line.base_tnd * rate / 100)
    line.movement_tnd = line.amount_tnd - line.previous_amount_tnd
    if justification is not None:
        line.justification = justification
    if fiscal_deductible is not None:
        line.fiscal_deductible = fiscal_deductible
    line.campaign.total_amount_tnd = sum((ln.amount_tnd for ln in line.campaign.lines), ZERO)


def validate(db: Session, user: User, c: ProvisionCampaign, approve: bool, comment: str | None = None) -> None:
    if c.status != "PROPOSEE":
        raise HTTPException(409, "Campagne déjà décidée")
    if c.created_by == user.id:
        raise HTTPException(403, "Séparation des fonctions : la campagne doit être validée par une autre personne que son auteur")
    if approve:
        missing = [ln for ln in c.lines if ln.rate != ln.suggested_rate and not (ln.justification or "").strip()]
        if missing:
            raise HTTPException(400, f"{len(missing)} ligne(s) dont le taux diffère de la suggestion sans justification")
        c.status = "VALIDEE"
        if c.method == get_param(db, "provision.statutory_method"):
            accounting.on_provision_campaign(db, c)
    else:
        c.status = "REJETEE"
    c.validated_by = user.id
    c.validated_at = now_utc()
    if comment:
        c.notes = ((c.notes or "") + f"\n[Décision] {comment}").strip()


def observed_loss_rates(db: Session) -> dict:
    """Aide au calibrage IFRS 9 : taux de perte historique observé
    (passages en perte / facturation TTC) par année d'émission."""
    from ..models import Adjustment, Allocation
    from sqlalchemy import func, extract
    out = []
    years = db.execute(select(extract("year", Invoice.issue_date)).where(Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE").distinct()).scalars()
    for y in sorted(int(x) for x in years):
        billed = db.execute(select(func.coalesce(func.sum(Invoice.total_ttc_tnd), 0)).where(
            Invoice.lifecycle == "VALIDEE", Invoice.doc_type == "FACTURE", extract("year", Invoice.issue_date) == y)).scalar()
        lost = db.execute(select(func.coalesce(func.sum(Allocation.amount_tnd), 0)).join(Adjustment, Allocation.adjustment_id == Adjustment.id)
                          .join(Invoice, Allocation.invoice_id == Invoice.id)
                          .where(Adjustment.kind.in_(["PASSAGE_PERTE", "ABANDON_CREANCE"]), Allocation.reversed_at.is_(None),
                                 extract("year", Invoice.issue_date) == y)).scalar()
        out.append({"year": y, "billed_tnd": billed, "written_off_tnd": lost,
                    "loss_rate_pct": round(float(lost / billed * 100), 3) if billed else None})
    return {"years": out, "note": "Indicateur historique global ; la matrice IFRS 9 doit aussi intégrer des informations prospectives (IFRS 9 §5.5.17)."}
