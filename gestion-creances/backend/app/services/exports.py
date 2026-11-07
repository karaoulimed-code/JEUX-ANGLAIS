"""Exports Excel, PDF et CSV génériques (colonnes typées)."""
import csv
import datetime as dt
import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def fmt_amount(v) -> str:
    if v is None or v == "":
        return ""
    return f"{Decimal(v):,.3f}".replace(",", " ").replace(".", ",")


def fmt_cell(v, kind: str | None) -> str:
    if v is None:
        return ""
    if kind == "amount":
        return fmt_amount(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.strftime("%d/%m/%Y")
    if kind == "pct" and isinstance(v, (int, float, Decimal)):
        return f"{float(v):.1f} %"
    return str(v)


def to_xlsx(title: str, columns: list[dict], rows: list[dict], subtitle: str = "", totals: dict | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    import re
    ws.title = (re.sub(r"[\\/*?:\[\]]", "-", title)[:31]) or "Etat"
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=14, color="1F3A5F")
    ws.append([subtitle])
    ws.append([])
    ws.append([c["label"] for c in columns])
    for i, _ in enumerate(columns, 1):
        cell = ws.cell(row=4, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows:
        vals = []
        for c in columns:
            v = r.get(c["key"])
            if isinstance(v, Decimal):
                v = float(v)
            vals.append(v)
        ws.append(vals)
    if totals:
        ws.append([float(totals[c["key"]]) if isinstance(totals.get(c["key"]), Decimal) else totals.get(c["key"], "") for c in columns])
        for i in range(1, len(columns) + 1):
            ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
    for i, c in enumerate(columns, 1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = c.get("width", 16)
        for row in ws.iter_rows(min_row=5, min_col=i, max_col=i):
            for cell in row:
                if c.get("kind") == "amount":
                    cell.number_format = '#,##0.000'
                elif c.get("kind") == "date":
                    cell.number_format = 'DD/MM/YYYY'
    ws.freeze_panes = "A5"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_csv(columns: list[dict], rows: list[dict], sep: str = ";", decimal_comma: bool = True) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=sep)
    w.writerow([c["label"] for c in columns])
    for r in rows:
        out = []
        for c in columns:
            v = r.get(c["key"])
            if isinstance(v, Decimal):
                v = f"{v:.3f}".replace(".", ",") if decimal_comma else f"{v:.3f}"
            elif isinstance(v, (dt.date, dt.datetime)):
                v = v.strftime("%d/%m/%Y")
            out.append("" if v is None else v)
        w.writerow(out)
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM : ouverture correcte dans Excel


def to_pdf(title: str, columns: list[dict], rows: list[dict], subtitle: str = "", totals: dict | None = None,
           company: str = "", footer_note: str = "") -> bytes:
    buf = io.BytesIO()
    pagesize = landscape(A4) if len(columns) > 6 else A4
    doc = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
                            title=title)
    st = getSampleStyleSheet()
    small = st["BodyText"].clone("small", fontSize=7.5, leading=9)
    story = [Paragraph(f"<b>{company}</b>", st["Normal"]), Paragraph(title, st["Title"])]
    if subtitle:
        story.append(Paragraph(subtitle, st["Normal"]))
    story.append(Spacer(1, 4 * mm))
    data = [[Paragraph(f"<b>{c['label']}</b>", small) for c in columns]]
    for r in rows:
        data.append([Paragraph(fmt_cell(r.get(c["key"]), c.get("kind")), small) for c in columns])
    if totals:
        data.append([Paragraph(f"<b>{fmt_cell(totals.get(c['key']), c.get('kind'))}</b>", small) for c in columns])
    t = Table(data, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B0B7C3")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F9")]),
    ]
    for i, c in enumerate(columns):
        if c.get("kind") in ("amount", "pct", "int"):
            style.append(("ALIGN", (i, 1), (i, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    story.append(t)
    if footer_note:
        story += [Spacer(1, 4 * mm), Paragraph(footer_note, small)]

    def on_page(canvas, doc_):
        canvas.setFont("Helvetica", 7)
        canvas.drawString(12 * mm, 7 * mm, f"Édité le {dt.datetime.now():%d/%m/%Y %H:%M}")
        canvas.drawRightString(pagesize[0] - 12 * mm, 7 * mm, f"Page {doc_.page}")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
