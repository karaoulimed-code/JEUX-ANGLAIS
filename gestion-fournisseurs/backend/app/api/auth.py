from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Company, User, UserSession
from ..permissions import PERMISSIONS, ROLES, matrix
from ..schemas import LoginIn, PasswordChange, UserIn, UserUpdate, ser
from ..security import (BusinessError, Ctx, check_password_policy, create_session, get_ctx, hash_password, need,
                        verify_password)
from ..services.common import audit, ctx_audit
from .deps import get_or_404

router = APIRouter(prefix="/api/auth", tags=["Authentification et utilisateurs"])


def _me(user: User, db: Session) -> dict:
    comp = db.get(Company, user.company_id)
    return {**ser(user), "role_label": ROLES.get(user.role),
            "permissions": sorted(p for p, r in PERMISSIONS.items() if user.role in r),
            "company": ser(comp)}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    now = datetime.utcnow()
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(423, "Compte temporairement verrouillé après plusieurs échecs. Réessayez plus tard.")
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=15)
                user.failed_logins = 0
            audit(db, user.company_id, user, "echec_connexion", "utilisateur", user.id, None, ip)
            db.commit()
        raise HTTPException(401, "Identifiants incorrects.")
    user.failed_logins, user.locked_until, user.last_login = 0, None, now
    token = create_session(db, user, ip)
    audit(db, user.company_id, user, "connexion", "utilisateur", user.id, None, ip)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "user": _me(user, db)}


@router.post("/logout")
def logout(ctx: Ctx = Depends(get_ctx)):
    for s in ctx.db.scalars(select(UserSession).where(UserSession.user_id == ctx.user.id,
                                                      UserSession.revoked.is_(False))):
        s.revoked = True
    ctx_audit(ctx, "deconnexion", "utilisateur", ctx.user.id)
    ctx.db.commit()
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx)):
    return _me(ctx.user, ctx.db)


@router.post("/password")
def change_password(body: PasswordChange, ctx: Ctx = Depends(get_ctx)):
    if not verify_password(body.old_password, ctx.user.password_hash):
        raise BusinessError("Ancien mot de passe incorrect.")
    check_password_policy(body.new_password)
    ctx.user.password_hash = hash_password(body.new_password)
    ctx_audit(ctx, "changement_mot_de_passe", "utilisateur", ctx.user.id)
    ctx.db.commit()
    return {"ok": True}


@router.get("/roles")
def roles(ctx: Ctx = Depends(get_ctx)):
    return {"roles": ROLES, "matrice": matrix()}


@router.get("/users")
def list_users(ctx: Ctx = Depends(need("read"))):
    return [ser(u) for u in ctx.db.scalars(select(User).where(User.company_id == ctx.company_id).order_by(User.full_name))]


@router.post("/users")
def create_user(body: UserIn, ctx: Ctx = Depends(need("users.manage"))):
    if body.role not in ROLES:
        raise BusinessError("Rôle inconnu.")
    check_password_policy(body.password)
    if ctx.db.scalar(select(User).where(User.email == body.email.lower())):
        raise BusinessError("Adresse e-mail déjà utilisée.", status=409)
    u = User(company_id=ctx.company_id, email=body.email.lower(), full_name=body.full_name, role=body.role,
             password_hash=hash_password(body.password), language=body.language)
    ctx.db.add(u)
    ctx.db.flush()
    ctx_audit(ctx, "creation", "utilisateur", u.id, {"email": u.email, "role": u.role})
    ctx.db.commit()
    return ser(u)


@router.patch("/users/{uid}")
def update_user(uid: int, body: UserUpdate, ctx: Ctx = Depends(need("users.manage"))):
    u = get_or_404(ctx, User, uid, "Utilisateur")
    changes = {}
    if body.role is not None:
        if body.role not in ROLES:
            raise BusinessError("Rôle inconnu.")
        changes["role"] = [u.role, body.role]
        u.role = body.role
    if body.full_name is not None:
        u.full_name = body.full_name
    if body.language is not None:
        u.language = body.language
    if body.is_active is not None:
        if u.id == ctx.user.id and not body.is_active:
            raise BusinessError("Vous ne pouvez pas désactiver votre propre compte.")
        changes["actif"] = [u.is_active, body.is_active]
        u.is_active = body.is_active
    if body.password:
        check_password_policy(body.password)
        u.password_hash = hash_password(body.password)
        changes["mot_de_passe"] = "réinitialisé"
    ctx_audit(ctx, "modification", "utilisateur", u.id, changes)
    ctx.db.commit()
    return ser(u)
