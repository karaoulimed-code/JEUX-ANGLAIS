"""Exports Excel (.xlsx), CSV et PDF de tout état tabulaire."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def fmt(v):
    if isinstance(v, Decimal):
        return f"{v:,.3f}".replace(",", " ").replace(".", ",")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, (list, tuple)):
        return " ; ".join(str(x) for x in v)
    return "" if v is None else str(v)


def to_csv(columns: list[tuple[str, str]], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([c[1] for c in columns])
    for r in rows:
        w.writerow([fmt(r.get(c[0])) for c in columns])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM pour Excel


def to_xlsx(title: str, columns: list[tuple[str, str]], rows: list[dict], subtitle: str = "") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "".join(c for c in title if c not in "\\/*?:[]")[:30]
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([subtitle or f"Édité le {datetime.now():%d/%m/%Y %H:%M}"])
    ws.append([])
    ws.append([c[1] for c in columns])
    for i in range(1, len(columns) + 1):
        cell = ws.cell(row=4, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for r in rows:
        vals = []
        for c in columns:
            v = r.get(c[0])
            if isinstance(v, Decimal):
                v = float(v)
            elif isinstance(v, (list, tuple, dict)):
                v = fmt(v)
            vals.append(v)
        ws.append(vals)
    for i, c in enumerate(columns, 1):
        sample = [r.get(c[0]) for r in rows[:50]]
        if any(isinstance(v, Decimal) for v in sample):
            for row in ws.iter_rows(min_row=5, min_col=i, max_col=i):
                row[0].number_format = "#,##0.000"
        if any(isinstance(v, date) for v in sample):
            for row in ws.iter_rows(min_row=5, min_col=i, max_col=i):
                row[0].number_format = "DD/MM/YYYY"
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(45, len(c[1]) + 4))
    ws.freeze_panes = "A5"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(title: str, columns: list[tuple[str, str]], rows: list[dict], subtitle: str = "") -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=25, bottomMargin=25,
                            title=title)
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=7, leading=8.5)
    data = [[Paragraph(f"<b>{c[1]}</b>", small) for c in columns]]
    for r in rows:
        data.append([Paragraph(fmt(r.get(c[0])), small) for c in columns])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F9")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story = [Paragraph(title, styles["Title"]),
             Paragraph(subtitle or f"Édité le {datetime.now():%d/%m/%Y %H:%M}", styles["Normal"]),
             Spacer(1, 8), t]
    doc.build(story)
    return out.getvalue()


def render(fmt_: str, title: str, columns, rows, subtitle: str = "") -> tuple[bytes, str, str]:
    import unicodedata
    ascii_title = unicodedata.normalize("NFKD", title.lower()).encode("ascii", "ignore").decode()
    safe = "".join(ch if ch.isalnum() else "_" for ch in ascii_title)[:50]
    if fmt_ == "csv":
        return to_csv(columns, rows), "text/csv; charset=utf-8", f"{safe}.csv"
    if fmt_ == "pdf":
        return to_pdf(title, columns, rows, subtitle), "application/pdf", f"{safe}.pdf"
    return (to_xlsx(title, columns, rows, subtitle),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{safe}.xlsx")
