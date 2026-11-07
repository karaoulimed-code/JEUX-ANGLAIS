from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..models import AccountMapping, AuditLog, Company, ExchangeRate, Setting, TaxRate
from ..schemas import AccountMapIn, FxIn, SettingIn, TaxRateIn, ser
from ..security import BusinessError, Ctx, need
from ..services.common import (DEFAULT_ACCOUNTS, DEFAULT_SETTINGS, ctx_audit, get_setting, account,
                               verify_audit_chain)
from .deps import get_or_404

router = APIRouter(prefix="/api/admin", tags=["Paramétrage, audit"])


@router.get("/company")
def company(ctx: Ctx = Depends(need("read"))):
    return ser(ctx.db.get(Company, ctx.company_id))


@router.get("/settings")
def list_settings(ctx: Ctx = Depends(need("read"))):
    return [{"key": k, "value": get_setting(ctx.db, ctx.company_id, k), "label": lab, "defaut": dv}
            for k, (dv, lab) in DEFAULT_SETTINGS.items()]


@router.put("/settings/{key}")
def set_setting(key: str, body: SettingIn, ctx: Ctx = Depends(need("settings.manage"))):
    if key not in DEFAULT_SETTINGS:
        raise BusinessError("Paramètre inconnu.")
    if key == "date_cloture" and body.value:
        date.fromisoformat(body.value)
        if ctx.user.role not in ("resp_compta",):
            raise BusinessError("La clôture de période est réservée au responsable comptable.", status=403)
    s = ctx.db.scalar(select(Setting).where(Setting.company_id == ctx.company_id, Setting.key == key))
    old = s.value if s else DEFAULT_SETTINGS[key][0]
    if not s:
        s = Setting(company_id=ctx.company_id, key=key, label=DEFAULT_SETTINGS[key][1], value=body.value)
        ctx.db.add(s)
    s.value = body.value
    ctx_audit(ctx, "parametre", "parametre", key, {"avant": old, "apres": body.value})
    ctx.db.commit()
    return {"key": key, "value": s.value}


@router.get("/tax-rates")
def list_rates(ctx: Ctx = Depends(need("read"))):
    return [ser(t) for t in ctx.db.scalars(select(TaxRate).where(TaxRate.company_id == ctx.company_id)
                                           .order_by(TaxRate.kind, TaxRate.code, TaxRate.valid_from))]


@router.post("/tax-rates")
def add_rate(body: TaxRateIn, ctx: Ctx = Depends(need("settings.manage"))):
    t = TaxRate(company_id=ctx.company_id, **body.model_dump())
    ctx.db.add(t)
    ctx.db.flush()
    ctx_audit(ctx, "creation", "taux", t.id, body.model_dump())
    ctx.db.commit()
    return ser(t)


@router.patch("/tax-rates/{tid}")
def update_rate(tid: int, body: TaxRateIn, ctx: Ctx = Depends(need("settings.manage"))):
    """Bonne pratique : ne pas modifier un taux passé, mais clore sa validité (valid_to) et en créer un nouveau."""
    t = get_or_404(ctx, TaxRate, tid, "Taux")
    before = ser(t)
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    ctx_audit(ctx, "modification", "taux", t.id, {"avant": before, "apres": body.model_dump()})
    ctx.db.commit()
    return ser(t)


@router.get("/accounts")
def list_accounts(ctx: Ctx = Depends(need("read"))):
    return [{"key": k, "account_code": account(ctx.db, ctx.company_id, k), "label": lab, "defaut": dv}
            for k, (dv, lab) in DEFAULT_ACCOUNTS.items()]


@router.put("/accounts/{key}")
def set_account(key: str, body: AccountMapIn, ctx: Ctx = Depends(need("settings.manage"))):
    if key not in DEFAULT_ACCOUNTS:
        raise BusinessError("Clé de compte inconnue.")
    m = ctx.db.scalar(select(AccountMapping).where(AccountMapping.company_id == ctx.company_id, AccountMapping.key == key))
    old = m.account_code if m else DEFAULT_ACCOUNTS[key][0]
    if not m:
        m = AccountMapping(company_id=ctx.company_id, key=key, label=body.label or DEFAULT_ACCOUNTS[key][1],
                           account_code=body.account_code)
        ctx.db.add(m)
    m.account_code = body.account_code
    if body.label:
        m.label = body.label
    ctx_audit(ctx, "parametre_compte", "compte", key, {"avant": old, "apres": body.account_code})
    ctx.db.commit()
    return ser(m)


@router.get("/fx-rates")
def list_fx(ctx: Ctx = Depends(need("read"))):
    return [ser(f) for f in ctx.db.scalars(select(ExchangeRate).where(ExchangeRate.company_id == ctx.company_id)
                                           .order_by(ExchangeRate.rate_date.desc()))]


@router.post("/fx-rates")
def add_fx(body: FxIn, ctx: Ctx = Depends(need("read"))):
    if ctx.user.role not in ("tresorier", "resp_compta", "daf", "admin"):
        raise BusinessError("Saisie des cours réservée au trésorier, au comptable, au DAF ou à l'administrateur.", status=403)
    f = ctx.db.scalar(select(ExchangeRate).where(ExchangeRate.company_id == ctx.company_id,
                                                 ExchangeRate.currency == body.currency.upper(),
                                                 ExchangeRate.rate_date == body.rate_date))
    if f:
        old = f.rate
        f.rate, f.source = body.rate, body.source
    else:
        old = None
        f = ExchangeRate(company_id=ctx.company_id, **{**body.model_dump(), "currency": body.currency.upper()})
        ctx.db.add(f)
    ctx.db.flush()
    ctx_audit(ctx, "cours_change", "devise", f.id, {"devise": f.currency, "date": f.rate_date, "avant": old, "apres": f.rate})
    ctx.db.commit()
    return ser(f)


@router.get("/audit")
def audit_logs(entity: str | None = None, entity_id: str | None = None, limit: int = 300,
               ctx: Ctx = Depends(need("audit.read"))):
    q = select(AuditLog).where(AuditLog.company_id == ctx.company_id)
    if entity:
        q = q.where(AuditLog.entity == entity)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    return [ser(a) for a in ctx.db.scalars(q.order_by(AuditLog.id.desc()).limit(min(limit, 2000)))]


@router.get("/audit/verify")
def audit_verify(ctx: Ctx = Depends(need("audit.read"))):
    return verify_audit_chain(ctx.db)
