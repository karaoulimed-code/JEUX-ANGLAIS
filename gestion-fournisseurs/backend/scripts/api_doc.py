"""Génère docs/09-reference-api.md à partir du schéma OpenAPI (documentation interactive : /api/docs)."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402

spec = app.openapi()
groups = defaultdict(list)
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        groups[(op.get("tags") or ["Autres"])[0]].append((method.upper(), path, op.get("summary", "")))
out = ["# Référence de l'API", "", "_Générée depuis le schéma OpenAPI (`python scripts/api_doc.py`). Documentation interactive "
       "et essais en ligne : `/api/docs` (Swagger) et `/api/redoc`._", "",
       "Authentification : `POST /api/auth/login` renvoie un jeton à transmettre dans l'en-tête "
       "`Authorization: Bearer <jeton>`. Les erreurs métier renvoient `422` avec `{detail, code}` ; un droit insuffisant `403`.", ""]
n = 0
for tag in sorted(groups):
    out += [f"## {tag}", "", "| Méthode | Chemin | Fonction |", "|---|---|---|"]
    for m, p, s in sorted(groups[tag], key=lambda x: (x[1], x[0])):
        out.append(f"| {m} | `{p}` | {s} |")
        n += 1
    out.append("")
Path(__file__).resolve().parents[2].joinpath("docs", "09-reference-api.md").write_text("\n".join(out), encoding="utf-8")
print(n, "opérations")
