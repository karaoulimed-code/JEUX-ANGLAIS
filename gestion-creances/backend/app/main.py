"""Point d'entrée de l'API — documentation interactive sur /api/docs."""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, DBAPIError

from . import __version__
from .api import admin, analytics, customers, invoices, payments, recovery
from .config import get_settings

log = logging.getLogger("gpc")

app = FastAPI(
    title="Gestion du poste clients — API",
    version=__version__,
    description="API du logiciel de gestion intégrée des créances clients (PME tunisiennes). "
                "Tous les montants sont des chaînes décimales exactes (3 décimales pour le TND).",
    docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=False, expose_headers=["Content-Disposition"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = resp.headers.get("Cache-Control", "no-store")
    return resp


@app.exception_handler(IntegrityError)
async def integrity(request: Request, exc: IntegrityError):
    log.warning("Contrainte d'intégrité : %s", exc.orig)
    return JSONResponse({"detail": "Opération refusée : elle violerait une règle d'intégrité des données (doublon ou référence invalide)."}, 409)


@app.exception_handler(DBAPIError)
async def dberror(request: Request, exc: DBAPIError):
    msg = str(exc.orig).split("\n")[0]
    if "INTERDIT" in msg:
        return JSONResponse({"detail": msg.split("INTERDIT", 1)[1].strip(" :")}, 409)
    log.exception("Erreur base de données")
    return JSONResponse({"detail": "Erreur de base de données. L'opération a été annulée."}, 500)


for r in (admin.router, customers.router, invoices.router, payments.router, recovery.router, analytics.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/api/health", tags=["Système"])
def health():
    return {"status": "ok", "version": __version__}
