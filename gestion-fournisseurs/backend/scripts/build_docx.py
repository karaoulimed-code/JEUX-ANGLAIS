"""Compile la documentation Markdown en dossiers Word (.docx) mis en forme.

  python scripts/build_docx.py   ->  docs/livrables/*.docx
"""
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DOCS = Path(__file__).resolve().parents[2] / "docs"
OUT = DOCS / "livrables"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GOLD = RGBColor(0xC8, 0x96, 0x3E)


def shade(cell, hex_color):
    tc = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc.append(shd)


def add_field(paragraph, instr):
    run = paragraph.add_run()
    for tag, text in (("begin", None), (None, instr), ("separate", None), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|_[^_]+_)")


def add_inline(p, text, bold=False, size=None):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            r = p.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`"):
            r = p.add_run(part[1:-1]); r.font.name = "Consolas"; r.font.size = Pt(9); r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        elif part.startswith("["):
            r = p.add_run(re.match(r"\[([^\]]+)\]", part).group(1))
        elif part.startswith("_") and part.endswith("_") and len(part) > 2:
            r = p.add_run(part[1:-1]); r.italic = True
        else:
            r = p.add_run(part)
        if bold:
            r.bold = True
        if size:
            r.font.size = Pt(size)


def setup(doc: Document, title: str, subtitle: str):
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    for lvl, size in ((1, 16), (2, 13), (3, 11.5)):
        h = doc.styles[f"Heading {lvl}"]
        h.font.name = "Calibri"; h.font.size = Pt(size); h.font.color.rgb = NAVY; h.font.bold = True
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin = sec.bottom_margin = Cm(2)
    # page de garde
    for _ in range(6):
        doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(title); r.font.size = Pt(26); r.bold = True; r.font.color.rgb = NAVY
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(subtitle); r.font.size = Pt(14); r.font.color.rgb = GOLD
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Logiciel de gestion des dettes fournisseurs — PME tunisiennes"); r.font.size = Pt(12)
    for _ in range(10):
        doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f"Version 1.0 — {date.today():%d/%m/%Y}").font.size = Pt(11)
    p.runs[0].add_break(WD_BREAK.PAGE)
    h = doc.add_paragraph("Sommaire", style="Heading 1")
    add_field(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
    note = doc.add_paragraph()
    r = note.add_run("(Dans Word : clic droit sur le sommaire › Mettre à jour les champs.)"); r.italic = True; r.font.size = Pt(8.5)
    note.runs[0].add_break(WD_BREAK.PAGE)
    # pied de page
    fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = fp.add_run(f"{title} — page "); fr.font.size = Pt(8)
    add_field(fp, "PAGE")
    _ = h


def table(doc, rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows if not re.match(r"^\|?\s*:?-{2,}", r.strip())]
    n = max(len(r) for r in cells)
    t = doc.add_table(rows=len(cells), cols=n)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, r in enumerate(cells):
        for j in range(n):
            c = t.cell(i, j)
            c.text = ""
            add_inline(c.paragraphs[0], r[j] if j < len(r) else "", bold=(i == 0), size=9)
            if i == 0:
                shade(c, "1F3A5F")
                for run in c.paragraphs[0].runs:
                    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            elif i % 2 == 0:
                shade(c, "F2F5F9")
    doc.add_paragraph()


def convert(doc, md_path: Path, demote=0):
    lines = md_path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            lang = ln[3:].strip()
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            i += 1
            if lang == "mermaid":  # diagramme rendu dans la version Markdown ; texte équivalent présent dans le document
                continue
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.5)
            r = p.add_run("\n".join(block)); r.font.name = "Consolas"; r.font.size = Pt(8.5)
            continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i]); i += 1
            table(doc, rows)
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            lvl = min(len(m.group(1)) + demote, 3)
            doc.add_paragraph(m.group(2).replace("`", ""), style=f"Heading {lvl}")
            i += 1
            continue
        if re.match(r"^\s*[-*]\s+", ln):
            p = doc.add_paragraph(style="List Bullet")
            add_inline(p, re.sub(r"^\s*[-*]\s+", "", ln))
        elif re.match(r"^\s*\d+\.\s+", ln):
            p = doc.add_paragraph(style="List Number")
            add_inline(p, re.sub(r"^\s*\d+\.\s+", "", ln))
        elif ln.strip() in ("---", ""):
            pass
        else:
            img = re.search(r"captures/([\w-]+\.png)", ln)
            p = doc.add_paragraph()
            add_inline(p, ln.lstrip("- "))
            if img and (DOCS / "captures" / img.group(1)).exists():
                doc.add_picture(str(DOCS / "captures" / img.group(1)), width=Cm(16))
        i += 1


def build(name, title, subtitle, files):
    doc = Document()
    setup(doc, title, subtitle)
    for k, f in enumerate(files):
        if k:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        convert(doc, DOCS / f)
    OUT.mkdir(exist_ok=True)
    doc.save(OUT / name)
    print("écrit", OUT / name)


if __name__ == "__main__":
    build("Dossier_fonctionnel_et_technique.docx", "Dossier fonctionnel et technique",
          "Cahier des charges · Conception · Indicateurs · Référentiel réglementaire",
          ["01-cahier-des-charges.md", "02-conception-technique.md", "04-plan-developpement.md",
           "05-indicateurs.md", "08-referentiel-reglementaire.md"])
    build("Guide_installation_et_utilisateur.docx", "Guide d'installation et d'utilisation",
          "Déploiement · Sauvegarde · Mode opératoire par profil",
          ["06-guide-installation.md", "07-guide-utilisateur.md"])
