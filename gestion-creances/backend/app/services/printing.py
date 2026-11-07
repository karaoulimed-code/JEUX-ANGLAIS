"""Impression : facture / avoir et reçu de règlement (PDF)."""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Allocation, Invoice, Payment
from .exports import fmt_amount
from .params import get_param


def _header(db: Session, st):
    c = get_param(db, "company") or {}
    lines = [f"<b>{c.get('name', '')}</b>", c.get("address", ""), c.get("city", ""),
             f"Matricule fiscal : {c.get('tax_id', '')}" if c.get("tax_id") else "", c.get("phone", ""), c.get("email", "")]
    return Paragraph("<br/>".join(l for l in lines if l), st["Normal"])


def invoice_pdf(db: Session, inv: Invoice) -> bytes:
    st = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    cust = inv.customer
    title = ("FACTURE" if inv.doc_type == "FACTURE" else "FACTURE D'AVOIR") + (f" N° {inv.number}" if inv.number else " (BROUILLON – sans valeur)")
    client = Paragraph("<br/>".join(x for x in [f"<b>{cust.legal_name}</b>", cust.address or "", cust.city or "",
                                                f"Matricule fiscal : {cust.tax_id}" if cust.tax_id else "Matricule fiscal : —",
                                                f"Code client : {cust.code}"] if x), st["Normal"])
    story = [Table([[_header(db, st), client]], colWidths=[90 * mm, 90 * mm]), Spacer(1, 8 * mm), Paragraph(title, st["Title"]),
             Paragraph(f"Date : {inv.issue_date:%d/%m/%Y} — Échéance : {inv.due_date:%d/%m/%Y} — Devise : {inv.currency}", st["Normal"]),
             Spacer(1, 5 * mm)]
    data = [["Désignation", "Qté", "P.U. HT", "Remise %", "TVA %", "Total HT"]]
    for l in inv.lines:
        data.append([Paragraph(l.description, st["BodyText"]), fmt_amount(l.quantity), fmt_amount(l.unit_price), f"{l.discount_pct:g}",
                     f"{l.vat_rate:g}", fmt_amount(l.amount_ht)])
    t = Table(data, colWidths=[75 * mm, 18 * mm, 25 * mm, 18 * mm, 15 * mm, 29 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("ALIGN", (1, 1), (-1, -1), "RIGHT")]))
    story += [t, Spacer(1, 5 * mm)]
    tot = [["Total HT", fmt_amount(inv.total_ht)]]
    for tx in inv.taxes:
        lab = tx.label + (f" (base {fmt_amount(tx.base)})" if tx.kind == "TVA" else "")
        tot.append([lab, fmt_amount(tx.amount)])
    tot.append([f"NET À PAYER TTC ({inv.currency})", fmt_amount(inv.total_ttc)])
    tt = Table(tot, colWidths=[110 * mm, 40 * mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    story.append(tt)
    if len(inv.installments) > 1:
        story += [Spacer(1, 5 * mm), Paragraph("<b>Échéancier</b>", st["Normal"])]
        story.append(Table([["Échéance", "Montant"]] + [[f"{i.due_date:%d/%m/%Y}", fmt_amount(i.amount)] for i in inv.installments]))
    story += [Spacer(1, 8 * mm), Paragraph(
        "Mentions légales à compléter selon votre activité (registre national des entreprises, conditions de règlement, pénalités de retard). "
        "Vérifier la conformité au régime de facturation applicable, y compris l'éventuelle obligation de facturation électronique.",
        st["Italic"])]
    doc.build(story)
    return buf.getvalue()


def receipt_pdf(db: Session, p: Payment) -> bytes:
    st = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    cust = p.customer
    story = [_header(db, st), Spacer(1, 8 * mm), Paragraph(f"REÇU DE RÈGLEMENT N° {p.number}", st["Title"]),
             Paragraph(f"Reçu de <b>{cust.legal_name}</b> (code {cust.code}) le {p.receipt_date:%d/%m/%Y} la somme de "
                       f"<b>{fmt_amount(p.amount)} {p.currency}</b> par {p.method.label}"
                       + (f" n° {p.reference}" if p.reference else "") + (f", banque {p.bank_name}" if p.bank_name else "") + ".", st["Normal"])]
    if p.method_kind in ("CHEQUE", "EFFET"):
        story.append(Paragraph("<i>Règlement reçu sous réserve d'encaissement effectif (sauf bonne fin).</i>", st["Normal"]))
    allocs = list(db.execute(select(Allocation).where(Allocation.payment_id == p.id, Allocation.reversed_at.is_(None))).scalars())
    if allocs:
        story += [Spacer(1, 5 * mm), Paragraph("<b>Affectation</b>", st["Normal"])]
        story.append(Table([["Facture", "Montant affecté"]] + [[a.invoice.number, fmt_amount(a.amount)] for a in allocs]))
    if p.amount > p.allocated_amount and p.status not in ("REJETE", "ANNULE"):
        story.append(Paragraph(f"Montant non affecté (avance) : {fmt_amount(p.amount - p.allocated_amount)} {p.currency}", st["Normal"]))
    story += [Spacer(1, 15 * mm), Paragraph("Signature et cachet", st["Normal"])]
    doc.build(story)
    return buf.getvalue()
