"""Génère docs/03-schema-base-de-donnees.md à partir du modèle (source unique de vérité)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import models  # noqa: E402,F401
from app.db import Base  # noqa: E402

out = ["# Schéma de la base de données", "",
       "_Document généré automatiquement depuis `backend/app/models.py` (`python scripts/schema_doc.py`)._", "",
       "Conventions : montants `NUMERIC(18,3)` (dinar à 3 décimales), taux de change `NUMERIC(18,6)`, "
       "chaque table métier porte `company_id` (cloisonnement multi-entreprises).", "",
       "## Diagramme des relations", "", "```mermaid", "erDiagram"]
for t in Base.metadata.sorted_tables:
    for fk in t.foreign_keys:
        if fk.column.table.name not in ("companies", "users"):  # lisibilité
            out.append(f"    {fk.column.table.name} ||--o{{ {t.name} : \"{fk.parent.name}\"")
out += ["```", ""]
for t in Base.metadata.sorted_tables:
    out += [f"## `{t.name}`", "", "| Colonne | Type | Nul | Clé / référence |", "|---|---|---|---|"]
    for c in t.columns:
        ref = "PK" if c.primary_key else ", ".join(f"→ {fk.column.table.name}.{fk.column.name}" for fk in c.foreign_keys)
        out.append(f"| `{c.name}` | {c.type} | {'oui' if c.nullable else 'non'} | {ref} |")
    uqs = [", ".join(col.name for col in con.columns) for con in t.constraints if con.__class__.__name__ == "UniqueConstraint"]
    if uqs:
        out += ["", "Contraintes d'unicité : " + " ; ".join(f"({u})" for u in uqs)]
    out.append("")
Path(__file__).resolve().parents[2].joinpath("docs", "03-schema-base-de-donnees.md").write_text("\n".join(out), encoding="utf-8")
print("ok", len(Base.metadata.tables), "tables")
