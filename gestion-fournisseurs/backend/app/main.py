"""Point d'entrée de l'API — Gestion des dettes fournisseurs (Accounts Payable)."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import accounting, admin, auth, disputes, invoices, payments, purchasing, reports, suppliers
from .config import settings
from .security import BusinessError

app = FastAPI(
    title="Gestion des dettes fournisseurs — API",
    version="1.0.0",
    description="Cycle fournisseurs intégré : achats, réceptions, factures, contrôle à 3 niveaux, échéances, "
                "règlements, litiges, comptabilité, trésorerie et reporting. Documentation : /api/docs",
    docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


@app.exception_handler(BusinessError)
async def business_error(_: Request, exc: BusinessError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message, "code": exc.code, "data": exc.data},
                        )


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"] if x != "body")
        msgs.append(f"{loc} : {e['msg']}")
    return JSONResponse(status_code=422, content={"detail": "Données invalides — " + " ; ".join(msgs), "code": "validation"})


for r in (auth.router, suppliers.router, purchasing.router, invoices.router, invoices.att_router, payments.router,
          payments.treasury, disputes.router, accounting.router, reports.router, admin.router):
    app.include_router(r)


@app.get("/api/health", tags=["Système"])
def health():
    return {"statut": "ok", "version": app.version}


# Interface web compilée (déploiement mono-serveur pour une PME)
if settings.frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = settings.frontend_dist / full_path
        if full_path and f.is_file():
            return FileResponse(f)
        return FileResponse(settings.frontend_dist / "index.html")
