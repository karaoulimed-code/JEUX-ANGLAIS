from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select

from ..models import (Dispute, Invoice, Payment, PaymentAllocation, PurchaseOrder, Supplier)
from ..money import D, ZERO, r3
from ..security import Ctx, need
from ..services import analytics as an
from ..services.invoices import balance, display_status, disputed_amount
from ..services.purchasing import commitments
from .deps import file_response, today

router = APIRouter(prefix="/api/reports", tags=["Modules 5, 10, 11 - Échéancier, pilotage, reporting"])


@router.get("/dashboard")
def dashboard(as_of: date | None = None, ctx: Ctx = Depends(need("read"))):
    d = today(as_of)
    k = an.kpis(ctx, d)
    fc = an.forecast(ctx, d)
    aging = an.aged_balance(ctx, d)
    week = d + timedelta(days=7)
    due_week = ZERO
    for i in an._validated(ctx):
        b = balance(ctx.db, i)
        if b > 0 and i.due_date and d <= i.due_date <= week:
            due_week += b * D(i.exchange_rate)
    month_start = d.replace(day=1)
    paid_month = D(ctx.db.scalar(select(func.coalesce(func.sum(Payment.cash_amount * Payment.exchange_rate), 0)).where(
        Payment.company_id == ctx.company_id, Payment.status.in_(("emis", "debite")),
        Payment.payment_date >= month_start, Payment.payment_date <= d)))
    planned = D(ctx.db.scalar(select(func.coalesce(func.sum(Payment.cash_amount * Payment.exchange_rate), 0)).where(
        Payment.company_id == ctx.company_id, Payment.status.in_(("brouillon", "a_approuver", "approuve")))))
    n_disp = ctx.db.scalar(select(func.count(Dispute.id)).where(Dispute.company_id == ctx.company_id,
                                                                Dispute.status.in_(("ouvert", "en_cours"))))
    return {"date": d, "indicateurs": k, "echeance_7_jours": r3(due_week), "paiements_effectues_mois": r3(paid_month),
            "paiements_prevus": r3(planned), "litiges_ouverts": n_disp,
            "anciennete": aging["totaux"], "previsions": fc["horizons"], "previsions_mensuelles": fc["mensuel"],
            "tresorerie_disponible": fc["tresorerie_disponible"], "alertes": an.alerts(ctx, d)[:15]}


@router.get("/kpis")
def kpis(as_of: date | None = None, period_days: int = 365, ctx: Ctx = Depends(need("read"))):
    return an.kpis(ctx, today(as_of), period_days)


@router.get("/aging")
def aging(as_of: date | None = None, supplier_id: int | None = None, currency: str | None = None,
          category: str | None = None, ctx: Ctx = Depends(need("read"))):
    return an.aged_balance(ctx, today(as_of), supplier_id, currency, category)


@router.get("/forecast")
def forecast(as_of: date | None = None, ctx: Ctx = Depends(need("treasury.read"))):
    return an.forecast(ctx, today(as_of))


@router.get("/alerts")
def alerts(as_of: date | None = None, ctx: Ctx = Depends(need("read"))):
    return an.alerts(ctx, today(as_of))


@router.get("/ledger")
def ledger(supplier_id: int | None = None, date_to: date | None = None, ctx: Ctx = Depends(need("read"))):
    return an.ledger_movements(ctx, supplier_id, date_to)


@router.get("/trial-balance")
def trial_balance(date_from: date, date_to: date, ctx: Ctx = Depends(need("read"))):
    return an.trial_balance(ctx, date_from, date_to)


@router.get("/search")
def search(q: str, ctx: Ctx = Depends(need("read"))):
    like = f"%{q}%"
    cid = ctx.company_id
    res = []
    for s in ctx.db.scalars(select(Supplier).where(Supplier.company_id == cid, or_(
            Supplier.legal_name.ilike(like), Supplier.code.ilike(like), Supplier.tax_id.ilike(like))).limit(8)):
        res.append({"type": "fournisseur", "id": s.id, "libelle": f"{s.code} — {s.legal_name}", "lien": f"/fournisseurs/{s.id}"})
    for i in ctx.db.scalars(select(Invoice).where(Invoice.company_id == cid, or_(
            Invoice.internal_ref.ilike(like), Invoice.supplier_number.ilike(like))).limit(8)):
        res.append({"type": "facture", "id": i.id, "libelle": f"{i.internal_ref} — n°{i.supplier_number} ({i.total_ttc} {i.currency})",
                    "lien": f"/factures/{i.id}"})
    for p in ctx.db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id == cid, PurchaseOrder.number.ilike(like)).limit(5)):
        res.append({"type": "commande", "id": p.id, "libelle": p.number, "lien": f"/achats/commandes/{p.id}"})
    for p in ctx.db.scalars(select(Payment).where(Payment.company_id == cid, or_(
            Payment.number.ilike(like), Payment.reference.ilike(like))).limit(5)):
        res.append({"type": "reglement", "id": p.id, "libelle": f"{p.number} {p.reference or ''}", "lien": f"/reglements/{p.id}"})
    return res


# ------------------------------------------------------------ états éditables (Excel, PDF, CSV)
def _report(ctx: Ctx, name: str, d: date, date_from: date | None, supplier_id: int | None):
    df = date_from or d.replace(month=1, day=1)
    if name == "balance-agee":
        a = an.aged_balance(ctx, d, supplier_id)
        cols = [("code", "Code"), ("fournisseur", "Fournisseur"), ("non_echu", "Non échu"), ("1_30", "1-30 j"),
                ("31_60", "31-60 j"), ("61_90", "61-90 j"), ("91_180", "91-180 j"), ("plus_180", "> 180 j"),
                ("total_brut", "Total dettes"), ("avoirs_non_imputes", "Avoirs non imputés"),
                ("avances_non_imputees", "Avances non imputées"), ("total_net", "Solde net"), ("dont_litiges", "Dont litiges")]
        rows = a["lignes"] + [{"fournisseur": "TOTAL", **a["totaux"]}]
        return f"Balance âgée fournisseurs au {d:%d/%m/%Y}", cols, rows
    if name == "balance-auxiliaire":
        t = an.trial_balance(ctx, df, d)
        cols = [("code", "Code"), ("fournisseur", "Fournisseur"), ("solde_initial", "Solde initial"),
                ("debit", "Débit"), ("credit", "Crédit"), ("solde_final", "Solde final (créditeur)")]
        return f"Balance auxiliaire fournisseurs du {df:%d/%m/%Y} au {d:%d/%m/%Y}", cols, t["lignes"] + [{"fournisseur": "TOTAL", **t["totaux"]}]
    if name == "grand-livre":
        rows = [m for m in an.ledger_movements(ctx, supplier_id, d) if m["date"] >= df]
        cols = [("fournisseur", "Fournisseur"), ("date", "Date"), ("piece", "Pièce"), ("libelle", "Libellé"),
                ("debit", "Débit"), ("credit", "Crédit"), ("solde", "Solde cumulé")]
        return f"Grand livre auxiliaire fournisseurs au {d:%d/%m/%Y}", cols, rows
    if name == "journal-achats":
        rows = []
        for i in ctx.db.scalars(select(Invoice).where(Invoice.company_id == ctx.company_id, Invoice.validated_at.is_not(None),
                                                      Invoice.invoice_date >= df, Invoice.invoice_date <= d).order_by(Invoice.invoice_date)):
            sg = -1 if i.doc_type == "avoir" else 1
            rows.append({"date": i.invoice_date, "ref": i.internal_ref, "type": i.doc_type, "numero": i.supplier_number,
                         "fournisseur": i.supplier.legal_name, "devise": i.currency, "ht": sg * D(i.total_ht) * D(i.exchange_rate),
                         "tva": sg * D(i.total_tva) * D(i.exchange_rate), "timbre": sg * D(i.stamp_duty) * D(i.exchange_rate),
                         "ttc": sg * D(i.total_ttc_tnd), "statut": i.workflow_status})
        rows = [{k: (r3(v) if isinstance(v, type(D(0))) else v) for k, v in r.items()} for r in rows]
        cols = [("date", "Date"), ("ref", "Réf."), ("type", "Type"), ("numero", "N° fournisseur"), ("fournisseur", "Fournisseur"),
                ("devise", "Devise"), ("ht", "HT (TND)"), ("tva", "TVA (TND)"), ("timbre", "Timbre"), ("ttc", "TTC (TND)"), ("statut", "Statut")]
        return f"Journal des achats du {df:%d/%m/%Y} au {d:%d/%m/%Y}", cols, rows
    if name == "journal-reglements":
        rows = []
        for p in ctx.db.scalars(select(Payment).where(Payment.company_id == ctx.company_id,
                                                      Payment.status.in_(("emis", "debite", "rejete")),
                                                      Payment.payment_date >= df, Payment.payment_date <= d).order_by(Payment.payment_date)):
            rows.append({"date": p.payment_date, "numero": p.number, "fournisseur": p.supplier.legal_name, "moyen": p.method,
                         "reference": p.reference, "type": p.kind, "montant_tnd": r3(D(p.cash_amount) * D(p.exchange_rate)),
                         "rs_tnd": r3(D(p.rs_amount) * D(p.exchange_rate)), "statut": p.status})
        cols = [("date", "Date"), ("numero", "N°"), ("fournisseur", "Fournisseur"), ("moyen", "Moyen"), ("reference", "Référence"),
                ("type", "Type"), ("montant_tnd", "Décaissé (TND)"), ("rs_tnd", "Retenue (TND)"), ("statut", "Statut")]
        return f"Journal des règlements du {df:%d/%m/%Y} au {d:%d/%m/%Y}", cols, rows
    if name in ("factures-non-reglees", "factures-litigieuses", "echeancier"):
        rows = []
        for i in an._validated(ctx):
            b = balance(ctx.db, i)
            st = display_status(ctx.db, i, d)
            if b <= 0 or (name == "factures-litigieuses" and st != "en_litige"):
                continue
            if supplier_id and i.supplier_id != supplier_id:
                continue
            rows.append({"echeance": i.due_date, "ref": i.internal_ref, "numero": i.supplier_number, "fournisseur": i.supplier.legal_name,
                         "date": i.invoice_date, "devise": i.currency, "ttc": i.total_ttc, "solde": b,
                         "solde_tnd": r3(b * D(i.exchange_rate)), "conteste": disputed_amount(ctx.db, i), "statut": st,
                         "retard": max((d - i.due_date).days, 0) if i.due_date else 0})
        rows.sort(key=lambda r: r["echeance"] or d)
        cols = [("echeance", "Échéance"), ("ref", "Réf."), ("numero", "N° fournisseur"), ("fournisseur", "Fournisseur"),
                ("date", "Date facture"), ("devise", "Devise"), ("ttc", "TTC"), ("solde", "Solde"), ("solde_tnd", "Solde TND"),
                ("conteste", "Contesté"), ("retard", "Retard (j)"), ("statut", "Statut")]
        title = {"factures-non-reglees": "État des factures non réglées", "factures-litigieuses": "État des factures litigieuses",
                 "echeancier": "Échéancier des paiements fournisseurs"}[name]
        return f"{title} au {d:%d/%m/%Y}", cols, rows
    if name == "engagements":
        cols = [("numero", "Bon de commande"), ("fournisseur", "Fournisseur"), ("date_commande", "Date"),
                ("livraison_prevue", "Livraison prévue"), ("restant_ttc_tnd", "Restant TTC (TND)"),
                ("recu_non_facture_ht", "Reçu non facturé HT"), ("statut", "Statut")]
        return "État des engagements non facturés", cols, commitments(ctx)
    if name == "avances":
        rows = []
        for p in ctx.db.scalars(select(Payment).where(Payment.company_id == ctx.company_id, Payment.kind == "avance",
                                                      Payment.status.in_(("emis", "debite")))):
            used = sum((D(a.amount) for a in p.allocations if not a.cancelled), ZERO)
            rows.append({"date": p.payment_date, "numero": p.number, "fournisseur": p.supplier.legal_name, "devise": p.currency,
                         "montant": r3(D(p.cash_amount) + D(p.rs_amount)), "impute": r3(used),
                         "reste": r3(D(p.cash_amount) + D(p.rs_amount) - used)})
        cols = [("date", "Date"), ("numero", "N°"), ("fournisseur", "Fournisseur"), ("devise", "Devise"),
                ("montant", "Montant"), ("impute", "Imputé"), ("reste", "Reste à imputer")]
        return "État des avances fournisseurs", cols, rows
    if name == "retenues-source":
        rows = []
        q = (select(PaymentAllocation, Payment, Invoice).join(Payment, Payment.id == PaymentAllocation.payment_id)
             .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
             .where(Payment.company_id == ctx.company_id, Payment.status.in_(("emis", "debite")),
                    PaymentAllocation.cancelled.is_(False), Payment.payment_date >= df, Payment.payment_date <= d))
        for a, p, i in ctx.db.execute(q):
            if not D(a.rs_amount):
                continue
            s = i.supplier
            rows.append({"date": p.payment_date, "reglement": p.number, "fournisseur": s.legal_name, "matricule": s.tax_id,
                         "facture": i.supplier_number, "code_rs": i.rs_code, "taux": i.rs_rate,
                         "base_ttc": r3(D(a.amount) * D(i.exchange_rate)), "retenue": r3(D(a.rs_amount) * D(i.exchange_rate))})
        cols = [("date", "Date paiement"), ("reglement", "Règlement"), ("fournisseur", "Bénéficiaire"), ("matricule", "Matricule fiscal"),
                ("facture", "Facture"), ("code_rs", "Nature"), ("taux", "Taux %"), ("base_ttc", "Montant brut (TND)"),
                ("retenue", "Retenue (TND)")]
        return f"État des retenues à la source du {df:%d/%m/%Y} au {d:%d/%m/%Y}", cols, rows
    if name == "previsions":
        fc = an.forecast(ctx, d)
        sups = {s.id: s.legal_name for s in ctx.db.scalars(select(Supplier).where(Supplier.company_id == ctx.company_id))}
        rows = [{**i, "fournisseur": sups.get(i["supplier_id"])} for i in fc["detail"]]
        cols = [("date", "Date prévue"), ("categorie", "Catégorie"), ("source", "Origine"), ("ref", "Référence"),
                ("fournisseur", "Fournisseur"), ("montant", "Montant (TND)")]
        return f"Prévisions de décaissements au {d:%d/%m/%Y}", cols, rows
    if name == "risques":
        cols = [("code", "Code"), ("fournisseur", "Fournisseur"), ("categorie", "Catégorie"), ("part_achats_pct", "Part achats %"),
                ("score", "Score"), ("niveau", "Niveau"), ("facteurs", "Facteurs")]
        return f"Analyse des risques fournisseurs au {d:%d/%m/%Y}", cols, an.supplier_risk(ctx, d)
    raise HTTPException(404, "État inconnu.")


REPORTS = ["balance-agee", "balance-auxiliaire", "grand-livre", "journal-achats", "journal-reglements",
           "factures-non-reglees", "factures-litigieuses", "engagements", "avances", "retenues-source",
           "echeancier", "previsions", "risques"]


@router.get("/catalog")
def catalog(ctx: Ctx = Depends(need("read"))):
    return REPORTS


@router.get("/export/{name}")
def export(name: str, format: str = "xlsx", as_of: date | None = None, date_from: date | None = None,
           supplier_id: int | None = None, ctx: Ctx = Depends(need("read"))):
    if format not in ("xlsx", "pdf", "csv", "json"):
        raise HTTPException(400, "Format : xlsx, pdf, csv ou json.")
    if name == "previsions":
        ctx.require("treasury.read")
    title, cols, rows = _report(ctx, name, today(as_of), date_from, supplier_id)
    if format == "json":
        return {"titre": title, "colonnes": cols, "lignes": rows}
    from ..models import Company
    comp = ctx.db.get(Company, ctx.company_id)
    sub = f"{comp.name}{' — DONNÉES DE DÉMONSTRATION' if comp.is_demo else ''}"
    return file_response(format, title, cols, rows, sub)
