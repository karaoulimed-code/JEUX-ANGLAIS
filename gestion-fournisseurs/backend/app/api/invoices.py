import csv
import hashlib
import io
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from openpyxl import load_workbook
from sqlalchemy import or_, select

from ..ai import extractor
from ..config import settings
from ..models import (Attachment, CreditAllocation, Dispute, Invoice, InvoiceApproval, Payment,
                      PaymentAllocation, Supplier)
from ..money import D
from ..schemas import ApproveIn, CreditAllocIn, InvoiceIn, InvoiceUpdate, ReasonIn, ser
from ..security import BusinessError, Ctx, need
from ..services import invoices as svc
from ..services.common import ctx_audit
from ..services.payments import payable_amount
from ..services.suppliers import normalize_tax_id
from .deps import get_or_404

router = APIRouter(prefix="/api/invoices", tags=["Modules 3, 4, 7 - Factures, contrôles, avoirs"])
att_router = APIRouter(prefix="/api/attachments", tags=["Pièces justificatives"])

ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff",
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/csv",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _detail(ctx: Ctx, inv: Invoice) -> dict:
    sup = ctx.db.get(Supplier, inv.supplier_id)
    allocs = []
    for a in ctx.db.scalars(select(PaymentAllocation).where(PaymentAllocation.invoice_id == inv.id)):
        p = ctx.db.get(Payment, a.payment_id)
        allocs.append(ser(a, paiement=p.number, statut_paiement=p.status, moyen=p.method))
    return ser(inv, fournisseur=sup.legal_name, fournisseur_code=sup.code,
               statut=svc.display_status(ctx.db, inv), solde=svc.balance(ctx.db, inv),
               montant_regle=svc.settled_amount(ctx.db, inv), montant_conteste=svc.disputed_amount(ctx.db, inv),
               payable=payable_amount(ctx.db, inv) if inv.workflow_status == "validee" and inv.doc_type != "avoir" else None,
               credit_disponible=svc.available_credit(ctx.db, inv) if inv.doc_type in ("avoir", "acompte") else None,
               lines=[ser(l) for l in inv.lines],
               approbations=[ser(a) for a in ctx.db.scalars(select(InvoiceApproval).where(InvoiceApproval.invoice_id == inv.id))],
               affectations=allocs,
               imputations=[ser(c) for c in ctx.db.scalars(select(CreditAllocation).where(
                   or_(CreditAllocation.target_invoice_id == inv.id, CreditAllocation.source_invoice_id == inv.id)))],
               litiges=[ser(d) for d in ctx.db.scalars(select(Dispute).where(Dispute.invoice_id == inv.id))],
               pieces=[ser(a) for a in ctx.db.scalars(select(Attachment).where(
                   Attachment.entity == "facture", Attachment.entity_id == inv.id))])


@router.get("")
def list_invoices(supplier_id: int | None = None, statut: str | None = None, doc_type: str | None = None,
                  q: str | None = None, due_from: date | None = None, due_to: date | None = None,
                  currency: str | None = None, ctx: Ctx = Depends(need("read"))):
    stmt = select(Invoice).where(Invoice.company_id == ctx.company_id)
    if supplier_id:
        stmt = stmt.where(Invoice.supplier_id == supplier_id)
    if doc_type:
        stmt = stmt.where(Invoice.doc_type == doc_type)
    if currency:
        stmt = stmt.where(Invoice.currency == currency)
    if due_from:
        stmt = stmt.where(Invoice.due_date >= due_from)
    if due_to:
        stmt = stmt.where(Invoice.due_date <= due_to)
    if q:
        like = f"%{q}%"
        stmt = stmt.join(Supplier, Supplier.id == Invoice.supplier_id).where(or_(
            Invoice.internal_ref.ilike(like), Invoice.supplier_number.ilike(like), Supplier.legal_name.ilike(like)))
    out = []
    for inv in ctx.db.scalars(stmt.order_by(Invoice.invoice_date.desc(), Invoice.id.desc())):
        st = svc.display_status(ctx.db, inv)
        if statut and st != statut:
            continue
        out.append(ser(inv, fournisseur=inv.supplier.legal_name, statut=st, solde=svc.balance(ctx.db, inv),
                       nb_anomalies_bloquantes=len(svc.blocking(inv.anomalies))))
    return out


@router.get("/{iid}")
def get_invoice(iid: int, ctx: Ctx = Depends(need("read"))):
    return _detail(ctx, get_or_404(ctx, Invoice, iid, "Facture"))


@router.post("")
def create_invoice(body: InvoiceIn, ctx: Ctx = Depends(need("invoice.create"))):
    inv = svc.create_invoice(ctx, body.model_dump())
    ctx.db.commit()
    return _detail(ctx, inv)


@router.patch("/{iid}")
def update_invoice(iid: int, body: InvoiceUpdate, ctx: Ctx = Depends(need("invoice.create"))):
    inv = svc.update_invoice(ctx, get_or_404(ctx, Invoice, iid, "Facture"), body.model_dump(exclude_unset=True))
    ctx.db.commit()
    return _detail(ctx, inv)


@router.post("/{iid}/controls")
def rerun_controls(iid: int, ctx: Ctx = Depends(need("read"))):
    inv = get_or_404(ctx, Invoice, iid, "Facture")
    res = svc.run_controls(ctx, inv)
    if inv.workflow_status in ("brouillon", "en_attente_validation"):
        inv.anomalies = res
        ctx.db.commit()
    return res


@router.post("/{iid}/submit")
def submit(iid: int, ctx: Ctx = Depends(need("invoice.create"))):
    inv = svc.submit_invoice(ctx, get_or_404(ctx, Invoice, iid, "Facture"))
    ctx.db.commit()
    return _detail(ctx, inv)


@router.post("/{iid}/approve")
def approve(iid: int, body: ApproveIn, ctx: Ctx = Depends(need("invoice.validate"))):
    inv = svc.approve_invoice(ctx, get_or_404(ctx, Invoice, iid, "Facture"), body.comment, body.force, body.justification)
    ctx.db.commit()
    return _detail(ctx, inv)


@router.post("/{iid}/reject")
def reject(iid: int, body: ReasonIn, ctx: Ctx = Depends(need("invoice.validate"))):
    inv = svc.reject_invoice(ctx, get_or_404(ctx, Invoice, iid, "Facture"), body.reason)
    ctx.db.commit()
    return _detail(ctx, inv)


@router.post("/{iid}/cancel")
def cancel(iid: int, body: ReasonIn, ctx: Ctx = Depends(need("invoice.create"))):
    inv = svc.cancel_invoice(ctx, get_or_404(ctx, Invoice, iid, "Facture"), body.reason)
    ctx.db.commit()
    return _detail(ctx, inv)


@router.post("/credit-allocations")
def credit_allocation(body: CreditAllocIn, ctx: Ctx = Depends(need("invoice.validate"))):
    src = get_or_404(ctx, Invoice, body.source_invoice_id, "Avoir")
    tgt = get_or_404(ctx, Invoice, body.target_invoice_id, "Facture")
    ca = svc.allocate_credit(ctx, src, tgt, body.amount, body.allocation_date)
    ctx.db.commit()
    return ser(ca)


# ------------------------------------------------------------ import Excel / CSV
IMPORT_COLUMNS = ["fournisseur", "numero", "date_facture", "date_reception", "montant_ht", "taux_tva",
                  "montant_tva", "timbre", "devise", "taux_change", "echeance", "description", "type"]


def _parse_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"date illisible « {s} » (format attendu JJ/MM/AAAA)")


def _parse_dec(v, default=None):
    if v in (None, ""):
        return default
    try:
        return Decimal(str(v).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"montant illisible « {v} »")


@router.get("/import/template")
def import_template():
    from fastapi import Response
    content = ";".join(IMPORT_COLUMNS) + "\nF001;FA-2026-118;15/10/2026;17/10/2026;1000,000;19;190,000;1,000;TND;;;Fournitures;facture\n"
    return Response(("﻿" + content).encode(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="modele_import_factures.csv"'})


@router.post("/import")
async def import_invoices(file: UploadFile = File(...), ctx: Ctx = Depends(need("invoice.create"))):
    """Import en brouillon : chaque facture importée reste soumise aux contrôles et à la validation."""
    raw = await file.read()
    rows: list[dict] = []
    if file.filename.lower().endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(raw), data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip().lower() if h else "" for h in next(it)]
        for r in it:
            if any(c not in (None, "") for c in r):
                rows.append(dict(zip(header, r)))
    else:
        text = raw.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,\t")
        rows = [{k.strip().lower(): v for k, v in r.items() if k} for r in csv.DictReader(io.StringIO(text), dialect=dialect)]
    created, errors = [], []
    for n, r in enumerate(rows, start=2):
        try:
            key = str(r.get("fournisseur") or "").strip()
            sup = ctx.db.scalar(select(Supplier).where(Supplier.company_id == ctx.company_id, or_(
                Supplier.code == key, Supplier.tax_id_normalized == normalize_tax_id(key))))
            if not sup:
                raise ValueError(f"fournisseur « {key} » inconnu (code ou matricule fiscal)")
            ht = _parse_dec(r.get("montant_ht"))
            if ht is None:
                raise ValueError("montant_ht obligatoire")
            rate = _parse_dec(r.get("taux_tva"), Decimal(19))
            tva = _parse_dec(r.get("montant_tva"))
            numero = str(r.get("numero") or "").strip()
            inv_date = _parse_date(r.get("date_facture"))
            if not numero or not inv_date:
                raise ValueError("numero et date_facture obligatoires")
            with ctx.db.begin_nested():
                inv = svc.create_invoice(ctx, {
                    "doc_type": (r.get("type") or "facture").strip().lower(), "supplier_id": sup.id,
                    "supplier_number": numero, "invoice_date": inv_date,
                    "reception_date": _parse_date(r.get("date_reception")),
                    "currency": (r.get("devise") or sup.currency).strip().upper(),
                    "exchange_rate": _parse_dec(r.get("taux_change")),
                    "stamp_duty": _parse_dec(r.get("timbre")), "due_date": _parse_date(r.get("echeance")),
                    "description": r.get("description"), "source": "import",
                    "lines": [{"description": r.get("description") or "Import", "quantity": Decimal(1),
                               "unit_price": ht, "tva_rate": rate, "amount_tva": tva}]})
            created.append({"ligne": n, "ref": inv.internal_ref, "anomalies": [a["code"] for a in inv.anomalies or []]})
        except (ValueError, BusinessError) as e:
            errors.append({"ligne": n, "erreur": getattr(e, "message", str(e))})
    ctx_audit(ctx, "import", "facture", None, {"fichier": file.filename, "crees": len(created), "erreurs": len(errors)})
    ctx.db.commit()
    return {"creees": created, "erreurs": errors}


@router.post("/ocr")
async def ocr(file: UploadFile = File(...), ctx: Ctx = Depends(need("invoice.create"))):
    try:
        res = extractor.extract(await file.read(), file.filename)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    return res


# ------------------------------------------------------------ pièces justificatives
ENTITIES = {"facture", "fournisseur", "commande", "reception", "reglement", "litige", "contrat"}


@att_router.post("")
async def upload(entity: str = Form(...), entity_id: int = Form(...), doc_type: str | None = Form(None),
                 file: UploadFile = File(...), ctx: Ctx = Depends(need("read"))):
    if ctx.user.role == "lecture":
        raise HTTPException(403, "Profil en consultation seule.")
    if entity not in ENTITIES:
        raise BusinessError("Type d'objet inconnu.")
    raw = await file.read()
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise BusinessError(f"Fichier trop volumineux (max {settings.max_upload_mb} Mo).")
    ctype = file.content_type or "application/octet-stream"
    if ctype not in ALLOWED_TYPES:
        raise BusinessError("Format non autorisé (PDF, images, Excel, Word, CSV).")
    digest = hashlib.sha256(raw).hexdigest()
    folder = settings.storage_dir / str(ctx.company_id) / entity
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}_{''.join(c for c in file.filename if c.isalnum() or c in '._-')[:80]}"
    path.write_bytes(raw)
    att = Attachment(company_id=ctx.company_id, entity=entity, entity_id=entity_id, filename=file.filename,
                     content_type=ctype, size=len(raw), sha256=digest, storage_path=str(path),
                     doc_type=doc_type, uploaded_by_id=ctx.user.id)
    ctx.db.add(att)
    ctx.db.flush()
    if entity == "facture":
        inv = get_or_404(ctx, Invoice, entity_id, "Facture")
        if inv.workflow_status in ("brouillon", "en_attente_validation"):
            inv.anomalies = svc.run_controls(ctx, inv)
    ctx_audit(ctx, "piece_jointe", entity, entity_id, {"fichier": file.filename, "sha256": digest})
    ctx.db.commit()
    return ser(att)


@att_router.get("/{aid}")
def download(aid: int, ctx: Ctx = Depends(need("read"))):
    att = get_or_404(ctx, Attachment, aid, "Pièce")
    return FileResponse(att.storage_path, media_type=att.content_type, filename=att.filename)


_ = D
