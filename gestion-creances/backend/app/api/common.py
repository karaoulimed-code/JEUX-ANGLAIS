import datetime as dt
import json
from decimal import Decimal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from ..models import Customer, User
from ..permissions import PORTFOLIO_SCOPED


def _default(o):
    if isinstance(o, Decimal):
        return format(o, "f")
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    raise TypeError(f"Type non sérialisable : {type(o)}")


class J(JSONResponse):
    """Réponse JSON où les montants restent des chaînes exactes (jamais de float)."""

    def render(self, content) -> bytes:
        return json.dumps(content, default=_default, ensure_ascii=False).encode("utf-8")


def out(data, status_code: int = 200) -> J:
    return J(content=data, status_code=status_code)


def ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def scoped(user: User) -> bool:
    return user.role in PORTFOLIO_SCOPED


def check_customer_access(db: Session, user: User, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(404, "Client introuvable")
    if scoped(user) and c.salesperson_id != user.id:
        raise HTTPException(403, "Ce client n'appartient pas à votre portefeuille")
    return c


def file_response(content: bytes, filename: str, media: str) -> Response:
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
}
