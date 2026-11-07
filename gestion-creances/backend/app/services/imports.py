"""Import de clients et de factures depuis Excel (.xlsx) ou CSV.

Le mode « simulation » (dry_run) contrôle tout le fichier et renvoie un
rapport ligne par ligne sans rien enregistrer. L'import réel est atomique :
si une ligne est en erreur, rien n'est importé.
"""
import csv
import datetime as dt
import io
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import ZERO, q3, q6
from ..models import Customer, Installment, Invoice, InvoiceTax, InvoiceLine, User, now_utc
from . import accounting
from .invoices import find_duplicates, get_rate

INVOICE_COLUMNS = ["numero", "date", "code_client", "echeance", "montant_ht", "tva", "autres_taxes", "montant_ttc", "devise", "cours",
                   "reference_externe", "type"]
CUSTOMER_COLUMNS = ["code", "raison_sociale", "nom_commercial", "matricule_fiscal", "adresse", "ville", "telephone", "email",
                    "activite", "secteur", "categorie", "zone", "groupe", "contact", "delai_paiement_jours", "plafond_credit", "encours_max"]


def read_table(filename: str, content: bytes) -> list[dict]:
    name = filename.lower()
    if name.endswith(".xlsx"):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        head = [str(h or "").strip().lower() for h in rows[0]]
        return [dict(zip(head, r)) for r in rows[1:] if any(v not in (None, "") for v in r)]
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        sep = ";" if text.count(";") >= text.count(",") else ","
        rd = csv.DictReader(io.StringIO(text), delimiter=sep)
        return [{(k or "").strip().lower(): v for k, v in r.items()} for r in rd]
    raise HTTPException(400, "Format non pris en charge (xlsx ou csv)")


def _dec(v, field, errors) -> Decimal:
    if v in (None, ""):
        return ZERO
    try:
        if isinstance(v, (int, float, Decimal)):
            return q3(v)
        return q3(Decimal(str(v).replace(" ", "").replace(" ", "").replace(",", ".")))
    except InvalidOperation:
        errors.append(f"{field} : nombre invalide « {v} »")
        return ZERO


def _date(v, field, errors) -> dt.date | None:
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(str(v).strip(), f).date()
        except ValueError:
            pass
    errors.append(f"{field} : date invalide « {v} » (format attendu JJ/MM/AAAA)")
    return None


def import_invoices(db: Session, user: User, filename: str, content: bytes, dry_run: bool) -> dict:
    rows = read_table(filename, content)
    report = []
    seen = set()
    created = 0
    custs = {c.code: c for c in db.execute(select(Customer)).scalars()}
    for n, r in enumerate(rows, start=2):
        err: list[str] = []
        warn: list[str] = []
        number = str(r.get("numero") or "").strip()
        doc_type = (str(r.get("type") or "FACTURE").strip().upper() or "FACTURE")
        if doc_type not in ("FACTURE", "AVOIR"):
            err.append("type : FACTURE ou AVOIR")
        cust = custs.get(str(r.get("code_client") or "").strip())
        if not number:
            err.append("numero obligatoire")
        if not cust:
            err.append(f"client inconnu « {r.get('code_client')} »")
        d = _date(r.get("date"), "date", err)
        due = _date(r.get("echeance"), "echeance", err) or (d + dt.timedelta(days=cust.payment_terms_days) if d and cust else None)
        ht, tva, other, ttc = (_dec(r.get(k), k, err) for k in ("montant_ht", "tva", "autres_taxes", "montant_ttc"))
        if ttc <= 0:
            err.append("montant_ttc doit être positif")
        if ht + tva + other != ttc:
            err.append(f"incohérence HT + TVA + autres taxes ({ht + tva + other}) ≠ TTC ({ttc})")
        currency = (str(r.get("devise") or "TND").strip().upper())
        if d and due and due < d:
            err.append("échéance antérieure à la date de facture")
        key = (doc_type, number)
        if key in seen:
            err.append("numéro en double dans le fichier")
        seen.add(key)
        if number and db.execute(select(Invoice.id).where(Invoice.doc_type == doc_type, Invoice.number == number)).first():
            err.append("numéro déjà existant dans le logiciel")
        rate = None
        if not err:
            try:
                rate = q6(r["cours"]) if r.get("cours") not in (None, "") else get_rate(db, currency, d)
            except HTTPException as e:
                err.append(e.detail)
        if not err and cust:
            ext = str(r.get("reference_externe") or "").strip() or None
            if find_duplicates(db, cust.id, d, ttc, ext):
                warn.append("doublon possible (même client, date et montant, ou même référence externe)")
        report.append({"line": n, "number": number, "errors": err, "warnings": warn})
        if err or dry_run:
            continue
        inv = Invoice(doc_type=doc_type, number=number, external_ref=str(r.get("reference_externe") or "").strip() or None,
                      source="IMPORT", customer_id=cust.id, issue_date=d, due_date=due, currency=currency, exchange_rate=rate,
                      total_ht=ht, total_vat=tva, total_other_taxes=other, total_ttc=ttc, total_ttc_tnd=q3(ttc * rate),
                      total_ht_tnd=q3(ht * rate), balance=ttc, lifecycle="VALIDEE", created_by=user.id, validated_by=user.id,
                      validated_at=now_utc(), salesperson_id=cust.salesperson_id, notes=f"Importé depuis {filename}")
        inv.customer = cust
        inv.lines.append(InvoiceLine(position=1, description="Facture importée", quantity=1, unit_price=ht, amount_ht=ht, vat_amount=tva))
        if tva:
            inv.taxes.append(InvoiceTax(code="TVA", label="TVA (import)", kind="TVA", base=ht, amount=tva))
        if other:
            inv.taxes.append(InvoiceTax(code="AUTRES", label="Timbre et autres taxes (import)", kind="AUTRE", base=ZERO, amount=other))
        if doc_type == "FACTURE":
            inv.installments.append(Installment(seq=1, due_date=due, amount=ttc, amount_tnd=inv.total_ttc_tnd))
        db.add(inv)
        db.flush()
        accounting.on_invoice_validated(db, inv)
        created += 1
    errors = sum(1 for x in report if x["errors"])
    if errors and not dry_run:
        db.rollback()
        return {"dry_run": False, "imported": 0, "errors": errors, "lines": report, "message": "Import annulé : corrigez les erreurs puis relancez"}
    return {"dry_run": dry_run, "imported": created, "errors": errors, "total": len(rows), "lines": report}


def import_customers(db: Session, user: User, filename: str, content: bytes, dry_run: bool) -> dict:
    rows = read_table(filename, content)
    report = []
    created = 0
    existing = {c for c in db.execute(select(Customer.code)).scalars()}
    seen = set()
    for n, r in enumerate(rows, start=2):
        err = []
        code = str(r.get("code") or "").strip()
        name = str(r.get("raison_sociale") or "").strip()
        if not code or not name:
            err.append("code et raison_sociale obligatoires")
        if code in existing or code in seen:
            err.append("code déjà existant")
        seen.add(code)
        terms = int(_dec(r.get("delai_paiement_jours") or 30, "delai_paiement_jours", err))
        limit = _dec(r.get("plafond_credit"), "plafond_credit", err)
        maxexp = _dec(r.get("encours_max"), "encours_max", err)
        report.append({"line": n, "code": code, "errors": err, "warnings": []})
        if err or dry_run:
            continue
        db.add(Customer(code=code, legal_name=name, trade_name=r.get("nom_commercial"), tax_id=r.get("matricule_fiscal"),
                        address=r.get("adresse"), city=r.get("ville"), phone=str(r.get("telephone") or "") or None,
                        email=r.get("email"), activity=r.get("activite"), sector_code=r.get("secteur"),
                        category_code=r.get("categorie"), zone_code=r.get("zone"), group_code=r.get("groupe"),
                        contact_name=r.get("contact"), payment_terms_days=terms, credit_limit=limit, max_exposure=maxexp))
        created += 1
    errors = sum(1 for x in report if x["errors"])
    if errors and not dry_run:
        db.rollback()
        return {"dry_run": False, "imported": 0, "errors": errors, "lines": report, "message": "Import annulé : corrigez les erreurs"}
    return {"dry_run": dry_run, "imported": created, "errors": errors, "total": len(rows), "lines": report}
