"""Authentification, utilisateurs, paramétrage et journal d'audit."""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..models import (AuditLog, Currency, DunningLevel, DunningTemplate, ExchangeRate, Parameter, PaymentMethod,
                      ReferenceValue, TaxRate, User, UserSession, now_utc)
from ..permissions import PERMISSIONS, ROLES
from ..security import (check_password_policy, create_session_token, get_current_user, hash_password, refresh_token, require,
                        verify_password)
from ..services.params import DEFAULTS, get_param
from .common import ip, out
from .schemas import LoginIn, ParamIn, PasswordChangeIn, UserIn

router = APIRouter()


def user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "role": u.role,
            "role_label": ROLES.get(u.role), "is_active": u.is_active, "must_change_password": u.must_change_password,
            "last_login_at": u.last_login_at, "locked": bool(u.locked_until and u.locked_until > now_utc())}


# ------------------------------------------------------------------ authentification
@router.post("/auth/login", tags=["Authentification"])
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    u = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    now = now_utc()
    if u and u.locked_until and u.locked_until > now:
        raise HTTPException(423, f"Compte verrouillé jusqu'à {u.locked_until.astimezone():%H:%M} après plusieurs échecs")
    if not u or not u.is_active or not verify_password(body.password, u.password_hash):
        if u:
            u.failed_attempts += 1
            if u.failed_attempts >= s.max_failed_logins:
                u.locked_until = now + dt.timedelta(minutes=s.lockout_minutes)
                u.failed_attempts = 0
            audit.log(db, u, "LOGIN_FAILED", "user", u.id, {}, ip(request))
            db.commit()
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    u.failed_attempts = 0
    u.locked_until = None
    u.last_login_at = now
    token = create_session_token(db, u, ip(request), request.headers.get("user-agent"))
    audit.log(db, u, "LOGIN", "user", u.id, {}, ip(request))
    db.commit()
    return out({"access_token": token, "token_type": "bearer", "user": user_dict(u),
                "permissions": sorted(PERMISSIONS.get(u.role, [])), "idle_minutes": s.session_idle_minutes})


@router.post("/auth/refresh", tags=["Authentification"])
def refresh(request: Request, user: User = Depends(get_current_user)):
    return out({"access_token": refresh_token(user, request.state.sid)})


@router.post("/auth/logout", tags=["Authentification"])
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sess = db.get(UserSession, request.state.sid)
    sess.revoked_at = now_utc()
    audit.log(db, user, "LOGOUT", "user", user.id, {}, ip(request))
    db.commit()
    return out({"ok": True})


@router.get("/auth/me", tags=["Authentification"])
def me(user: User = Depends(get_current_user)):
    return out({"user": user_dict(user), "permissions": sorted(PERMISSIONS.get(user.role, []))})


@router.post("/auth/change-password", tags=["Authentification"])
def change_password(body: PasswordChangeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Mot de passe actuel incorrect")
    check_password_policy(body.new_password)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    audit.log(db, user, "PASSWORD_CHANGED", "user", user.id, {}, ip(request))
    db.commit()
    return out({"ok": True})


# ------------------------------------------------------------------ utilisateurs
@router.get("/users", tags=["Utilisateurs"])
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # liste minimale accessible à tous (choix d'un responsable, d'un commercial)
    users = db.execute(select(User).order_by(User.full_name)).scalars()
    full = "users.manage" in PERMISSIONS.get(user.role, set())
    return out([user_dict(u) if full else {"id": u.id, "full_name": u.full_name, "role": u.role} for u in users])


@router.get("/roles", tags=["Utilisateurs"])
def roles(user: User = Depends(get_current_user)):
    return out([{"code": k, "label": v, "permissions": sorted(PERMISSIONS[k])} for k, v in ROLES.items()])


@router.post("/users", tags=["Utilisateurs"])
def create_user(body: UserIn, request: Request, user: User = Depends(require("users.manage")), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(400, "Rôle inconnu")
    if db.execute(select(User).where(User.username == body.username)).first():
        raise HTTPException(409, "Identifiant déjà utilisé")
    if not body.password:
        raise HTTPException(400, "Mot de passe initial requis")
    check_password_policy(body.password)
    u = User(username=body.username, full_name=body.full_name, email=body.email, role=body.role,
             password_hash=hash_password(body.password), is_active=body.is_active, must_change_password=True)
    db.add(u)
    db.flush()
    audit.log(db, user, "USER_CREATED", "user", u.id, {"username": u.username, "role": u.role}, ip(request))
    db.commit()
    return out(user_dict(u), 201)


@router.put("/users/{uid}", tags=["Utilisateurs"])
def update_user(uid: int, body: UserIn, request: Request, user: User = Depends(require("users.manage")), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    if body.role not in ROLES:
        raise HTTPException(400, "Rôle inconnu")
    if u.id == user.id and (body.role != u.role or not body.is_active):
        raise HTTPException(409, "Vous ne pouvez pas modifier votre propre rôle ni désactiver votre compte")
    before = user_dict(u)
    u.full_name, u.email, u.role, u.is_active = body.full_name, body.email, body.role, body.is_active
    if body.password:
        check_password_policy(body.password)
        u.password_hash = hash_password(body.password)
        u.must_change_password = True
        u.locked_until = None
    if not u.is_active:
        for s in db.execute(select(UserSession).where(UserSession.user_id == u.id, UserSession.revoked_at.is_(None))).scalars():
            s.revoked_at = now_utc()
    audit.log(db, user, "USER_UPDATED", "user", u.id, {"before": before, "after": user_dict(u), "password_reset": bool(body.password)}, ip(request))
    db.commit()
    return out(user_dict(u))


# ------------------------------------------------------------------ paramétrage
@router.get("/params", tags=["Paramétrage"])
def list_params(user: User = Depends(require("params.read")), db: Session = Depends(get_db)):
    rows = list(db.execute(select(Parameter).order_by(Parameter.key, Parameter.valid_from.desc())).scalars())
    keys = sorted(set(DEFAULTS) | {r.key for r in rows})
    res = []
    for k in keys:
        hist = [r for r in rows if r.key == k]
        current = get_param(db, k)
        cur_row = next((r for r in hist if r.valid_from <= dt.date.today()), None)
        res.append({"key": k, "value": current, "valid_from": cur_row.valid_from if cur_row else None,
                    "description": cur_row.description if cur_row else None, "source": cur_row.source if cur_row else None,
                    "to_validate": cur_row.to_validate if cur_row else False,
                    "history": [{"value": r.value, "valid_from": r.valid_from, "updated_at": r.updated_at} for r in hist]})
    return out(res)


@router.put("/params/{key}", tags=["Paramétrage"])
def set_param(key: str, body: ParamIn, request: Request, user: User = Depends(require("params.write")), db: Session = Depends(get_db)):
    vf = body.valid_from or dt.date.today()
    row = db.execute(select(Parameter).where(Parameter.key == key, Parameter.valid_from == vf)).scalar_one_or_none()
    old = get_param(db, key, vf)
    prev_meta = db.execute(select(Parameter).where(Parameter.key == key).order_by(Parameter.valid_from.desc()).limit(1)).scalar_one_or_none()
    if row is None:
        row = Parameter(key=key, valid_from=vf,
                        description=prev_meta.description if prev_meta else None, source=prev_meta.source if prev_meta else None)
        db.add(row)
    row.value = body.value
    if body.description is not None:
        row.description = body.description
    if body.source is not None:
        row.source = body.source
    if body.to_validate is not None:
        row.to_validate = body.to_validate
    row.updated_by = user.id
    row.updated_at = now_utc()
    audit.log(db, user, "PARAM_CHANGED", "parameter", key, {"old": old, "new": body.value, "valid_from": vf}, ip(request))
    db.commit()
    return out({"ok": True})


SIMPLE = {
    "tax-rates": (TaxRate, ["code", "label", "kind", "rate", "fixed_amount", "account_code", "in_vat_base", "valid_from", "valid_to", "active", "source", "to_validate"]),
    "payment-methods": (PaymentMethod, ["code", "label", "kind", "requires_clearing", "account_code", "active"]),
    "currencies": (Currency, ["code", "label", "decimals", "active"]),
    "exchange-rates": (ExchangeRate, ["currency", "date", "rate", "source"]),
    "reference-values": (ReferenceValue, ["kind", "code", "label", "active"]),
    "dunning-levels": (DunningLevel, ["level", "code", "label", "days_after_due", "min_amount", "template_id", "escalate_to_legal", "active"]),
    "dunning-templates": (DunningTemplate, ["code", "label", "channel", "subject", "body", "active"]),
}


def _ser(obj, fields):
    d = {f: getattr(obj, f) for f in fields}
    pk = getattr(obj, "id", None)
    d["id"] = pk if pk is not None else getattr(obj, "code")
    return d


def _coerce(model, field, value):
    col = model.__table__.columns[field]
    if value in ("", None):
        return None
    t = col.type.python_type
    if t is dt.date and isinstance(value, str):
        return dt.date.fromisoformat(value)
    if t.__name__ == "Decimal":
        from decimal import Decimal
        return Decimal(str(value))
    if t is int:
        return int(value)
    return value


def _make_routes(name, model, fields):
    read_perm = "params.read" if name not in ("payment-methods", "currencies", "reference-values", "dunning-levels", "dunning-templates", "tax-rates") else None

    @router.get(f"/{name}", tags=["Paramétrage"], name=f"list_{name}")
    def _list(user: User = Depends(require(read_perm) if read_perm else get_current_user), db: Session = Depends(get_db)):
        q = select(model)
        return out([_ser(o, fields) for o in db.execute(q).scalars()])

    @router.post(f"/{name}", tags=["Paramétrage"], name=f"create_{name}")
    def _create(body: dict, request: Request, user: User = Depends(require("params.write")), db: Session = Depends(get_db)):
        obj = model(**{f: _coerce(model, f, body.get(f)) for f in fields if f in body})
        db.add(obj)
        db.flush()
        audit.log(db, user, "PARAM_CREATED", name, getattr(obj, "id", None) or getattr(obj, "code", None), body, ip(request))
        db.commit()
        return out(_ser(obj, fields), 201)

    @router.put(f"/{name}/{{oid}}", tags=["Paramétrage"], name=f"update_{name}")
    def _update(oid: str, body: dict, request: Request, user: User = Depends(require("params.write")), db: Session = Depends(get_db)):
        obj = db.get(model, int(oid) if oid.isdigit() and model is not Currency else oid)
        if not obj:
            raise HTTPException(404, "Élément introuvable")
        before = _ser(obj, fields)
        for f in fields:
            if f in body:
                setattr(obj, f, _coerce(model, f, body[f]))
        audit.log(db, user, "PARAM_UPDATED", name, oid, {"before": before, "after": body}, ip(request))
        db.commit()
        return out(_ser(obj, fields))


for _n, (_m, _f) in SIMPLE.items():
    _make_routes(_n, _m, _f)


# ------------------------------------------------------------------ audit
@router.get("/audit", tags=["Audit"])
def audit_list(entity_type: str | None = None, entity_id: str | None = None, username: str | None = None, action: str | None = None,
               limit: int = 200, offset: int = 0, user: User = Depends(require("audit.read")), db: Session = Depends(get_db)):
    q = select(AuditLog).order_by(AuditLog.id.desc())
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if username:
        q = q.where(AuditLog.username == username)
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    rows = db.execute(q.limit(min(limit, 1000)).offset(offset)).scalars()
    return out([{"id": r.id, "ts": r.ts, "username": r.username, "action": r.action, "entity_type": r.entity_type,
                 "entity_id": r.entity_id, "details": r.details, "ip": r.ip, "hash": r.hash[:12]} for r in rows])


@router.get("/audit/verify", tags=["Audit"])
def audit_verify(user: User = Depends(require("audit.read")), db: Session = Depends(get_db)):
    return out(audit.verify_chain(db))
