from datetime import date

from fastapi import HTTPException, Response

from ..security import Ctx
from ..services.exports import render


def get_or_404(ctx: Ctx, model, id_: int, label: str = "Élément"):
    obj = ctx.db.get(model, id_)
    if obj is None or getattr(obj, "company_id", ctx.company_id) != ctx.company_id:
        raise HTTPException(404, f"{label} introuvable.")
    return obj


def today(d: date | None) -> date:
    return d or date.today()


def file_response(fmt: str, title: str, columns, rows, subtitle: str = "") -> Response:
    content, mime, filename = render(fmt, title, columns, rows, subtitle)
    return Response(content, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
