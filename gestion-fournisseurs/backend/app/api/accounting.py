from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select

from ..models import Invoice, JournalEntry, PurchaseOrder, Supplier
from ..money import D, ZERO, r3
from ..schemas import ValidateEntriesIn, ser
from ..security import BusinessError, Ctx, need
from ..services import accounting as acc
from ..services.analytics import reconcile_aux_gl
from ..services.common import account, ctx_audit, fx_rate
from ..services.exports import to_csv
from ..services.invoices import balance
from ..services.purchasing import OPEN_PO
from .deps import today

router = APIRouter(prefix="/api/accounting", tags=["Module 9 - Comptabilité"])


def _je(ctx, je: JournalEntry) -> dict:
    lines = []
    for l in je.lines:
        s = ctx.db.get(Supplier, l.supplier_id) if l.supplier_id else None
        lines.append(ser(l, auxiliaire=s.code if s else None))
    return ser(je, lines=lines, total_debit=r3(sum((D(l.debit) for l in je.lines), ZERO)),
               total_credit=r3(sum((D(l.credit) for l in je.lines), ZERO)))


@router.get("/entries")
def entries(journal: str | None = None, status: str | None = None, date_from: date | None = None,
            date_to: date | None = None, ctx: Ctx = Depends(need("accounting.read"))):
    q = select(JournalEntry).where(JournalEntry.company_id == ctx.company_id)
    if journal:
        q = q.where(JournalEntry.journal == journal)
    if status:
        q = q.where(JournalEntry.status == status)
    if date_from:
        q = q.where(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.where(JournalEntry.entry_date <= date_to)
    return [_je(ctx, e) for e in ctx.db.scalars(q.order_by(JournalEntry.entry_date, JournalEntry.id))]


@router.post("/entries/validate")
def validate(body: ValidateEntriesIn, ctx: Ctx = Depends(need("accounting.validate"))):
    n = acc.validate_entries(ctx, body.ids)
    ctx.db.commit()
    return {"validees": n}


@router.get("/export")
def export(date_from: date | None = None, date_to: date | None = None, only_validated: bool = True,
           mark_exported: bool = False, ctx: Ctx = Depends(need("accounting.read"))):
    """Export générique (CSV ; séparateur « ; ») pour import dans le logiciel comptable."""
    q = select(JournalEntry).where(JournalEntry.company_id == ctx.company_id)
    if only_validated:
        q = q.where(JournalEntry.status == "validee")
    if date_from:
        q = q.where(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.where(JournalEntry.entry_date <= date_to)
    rows = []
    entries = list(ctx.db.scalars(q.order_by(JournalEntry.entry_date, JournalEntry.id)))
    for e in entries:
        for l in e.lines:
            s = ctx.db.get(Supplier, l.supplier_id) if l.supplier_id else None
            rows.append({"journal": e.journal, "date": e.entry_date, "piece": e.number, "compte": l.account_code,
                         "auxiliaire": s.code if s else "", "libelle": l.label, "debit": D(l.debit), "credit": D(l.credit)})
    if mark_exported:
        ctx.require("accounting.validate")
        for e in entries:
            e.exported_at = datetime.utcnow()
        ctx_audit(ctx, "export_comptable", "ecriture", None, {"nombre": len(entries)})
        ctx.db.commit()
    cols = [(k, k.capitalize()) for k in ("journal", "date", "piece", "compte", "auxiliaire", "libelle", "debit", "credit")]
    return Response(to_csv(cols, rows), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="ecritures_fournisseurs.csv"'})


@router.get("/reconciliation")
def reconciliation(as_of: date | None = None, external_gl_balance: Decimal | None = None,
                   ctx: Ctx = Depends(need("accounting.read"))):
    return reconcile_aux_gl(ctx, today(as_of), external_gl_balance)


@router.get("/balances")
def balances(as_of: date | None = None, ctx: Ctx = Depends(need("accounting.read"))):
    keys = ["fournisseurs", "fournisseurs_immo", "fournisseurs_effets", "fournisseurs_fnp", "avances_fournisseurs",
            "tva_deductible", "tva_deductible_immo", "retenue_source", "perte_change", "gain_change", "banque", "caisse"]
    out = []
    for k in keys:
        code = account(ctx.db, ctx.company_id, k)
        out.append({"cle": k, "compte": code, "solde_crediteur": acc.account_balance(ctx, code, today(as_of))})
    return out


# ------------------------------------------------------------ travaux de clôture
def _fnp_rows(ctx: Ctx) -> list[dict]:
    rows = []
    for po in ctx.db.scalars(select(PurchaseOrder).where(PurchaseOrder.company_id == ctx.company_id,
                                                         PurchaseOrder.status.in_(OPEN_PO + ("cloturee",)))):
        for l in po.lines:
            q = D(l.qty_received) - D(l.qty_invoiced)
            if q > 0:
                ht = r3(q * D(l.unit_price) * D(po.exchange_rate))
                rows.append({"bc": po.number, "supplier_id": po.supplier_id, "description": l.description,
                             "compte": l.account_code or account(ctx.db, ctx.company_id, "achats_defaut"),
                             "quantite": r3(q), "montant_ht_tnd": ht, "tva": r3(ht * D(l.tva_rate) / 100)})
    return rows


@router.get("/closing/fnp")
def fnp(ctx: Ctx = Depends(need("accounting.read"))):
    rows = _fnp_rows(ctx)
    return {"lignes": rows, "total_ht": r3(sum((r["montant_ht_tnd"] for r in rows), ZERO))}


@router.post("/closing/fnp")
def post_fnp(as_of: date, ctx: Ctx = Depends(need("accounting.validate"))):
    """Factures non parvenues : D charges (HT) + D TVA sur FNP / C 408 ; extourne au lendemain."""
    rows = _fnp_rows(ctx)
    if not rows:
        raise BusinessError("Aucune réception non facturée.")
    lab = f"Factures non parvenues au {as_of:%d/%m/%Y}"
    lines = []
    for r in rows:
        lines.append((r["compte"], None, f"{lab} {r['bc']}", r["montant_ht_tnd"], ZERO))
        lines.append((account(ctx.db, ctx.company_id, "tva_deductible"), None, f"{lab} TVA {r['bc']}", r["tva"], ZERO))
        lines.append((account(ctx.db, ctx.company_id, "fournisseurs_fnp"), r["supplier_id"], f"{lab} {r['bc']}",
                      ZERO, r["montant_ht_tnd"] + r["tva"]))
    je = acc._entry(ctx, "OD", as_of, lab, "fnp", None, lines)
    rev = acc._entry(ctx, "OD", as_of + timedelta(days=1), "Extourne " + lab, "fnp", None,
                     [(l.account_code, l.supplier_id, "Extourne " + l.label, D(l.credit), D(l.debit)) for l in je.lines],
                     reversal_of=je.id)
    ctx_audit(ctx, "ecriture_fnp", "ecriture", je.id, {"extourne": rev.id})
    ctx.db.commit()
    return {"ecriture": _je(ctx, je), "extourne": _je(ctx, rev)}


def _reval_rows(ctx: Ctx, as_of: date) -> list[dict]:
    rows = []
    for inv in ctx.db.scalars(select(Invoice).where(Invoice.company_id == ctx.company_id, Invoice.currency != "TND",
                                                    Invoice.validated_at.is_not(None))):
        bal = balance(ctx.db, inv, as_of)
        if bal == 0:
            continue
        rate = fx_rate(ctx.db, ctx.company_id, inv.currency, as_of)
        diff = r3(bal * (rate - D(inv.exchange_rate)))
        if diff:
            rows.append({"invoice_id": inv.id, "ref": inv.internal_ref, "supplier_id": inv.supplier_id,
                         "devise": inv.currency, "solde_devise": bal, "cours_historique": inv.exchange_rate,
                         "cours_cloture": rate, "ecart_tnd": diff})
    return rows


@router.get("/closing/fx-revaluation")
def fx_revaluation(as_of: date, ctx: Ctx = Depends(need("accounting.read"))):
    rows = _reval_rows(ctx, as_of)
    return {"lignes": rows, "perte_latente": r3(sum((r["ecart_tnd"] for r in rows if r["ecart_tnd"] > 0), ZERO)),
            "gain_latent": r3(-sum((r["ecart_tnd"] for r in rows if r["ecart_tnd"] < 0), ZERO)),
            "note": "Dettes en devises converties au cours de clôture (IAS 21 / NC 15). Le traitement des écarts "
                    "latents (résultat ou écarts de conversion au bilan) est à confirmer avec l'expert-comptable."}


@router.post("/closing/fx-revaluation")
def post_fx_revaluation(as_of: date, ctx: Ctx = Depends(need("accounting.validate"))):
    rows = _reval_rows(ctx, as_of)
    if not rows:
        raise BusinessError("Aucun écart de conversion.")
    lab = f"Actualisation dettes en devises au {as_of:%d/%m/%Y}"
    lines = []
    for r in rows:
        d = r["ecart_tnd"]
        sup_acc = account(ctx.db, ctx.company_id, "fournisseurs")
        if d > 0:
            lines += [(account(ctx.db, ctx.company_id, "perte_change"), None, f"{lab} {r['ref']}", d, ZERO),
                      (sup_acc, r["supplier_id"], f"{lab} {r['ref']}", ZERO, d)]
        else:
            lines += [(sup_acc, r["supplier_id"], f"{lab} {r['ref']}", -d, ZERO),
                      (account(ctx.db, ctx.company_id, "gain_change"), None, f"{lab} {r['ref']}", ZERO, -d)]
    je = acc._entry(ctx, "OD", as_of, lab, "reevaluation", None, lines)
    rev = acc._entry(ctx, "OD", as_of + timedelta(days=1), "Extourne " + lab, "reevaluation", None,
                     [(l.account_code, l.supplier_id, "Extourne " + l.label, D(l.credit), D(l.debit)) for l in je.lines],
                     reversal_of=je.id)
    ctx_audit(ctx, "reevaluation_change", "ecriture", je.id, {"extourne": rev.id})
    ctx.db.commit()
    return {"ecriture": _je(ctx, je), "extourne": _je(ctx, rev)}
