"""Authentification (mot de passe PBKDF2 + jeton JWT révocable), sessions, contexte."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, UserSession
from .permissions import has_permission

PBKDF2_ITER = 390_000


class BusinessError(Exception):
    """Violation d'une règle de gestion (renvoyée au client en 422)."""

    def __init__(self, message: str, code: str = "regle_gestion", status: int = 422, data=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.data = data


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


def check_password_policy(password: str) -> None:
    if len(password) < 10 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise BusinessError("Mot de passe : 10 caractères minimum, avec lettres et chiffres.")


def create_session(db: Session, user: User, ip: str | None) -> str:
    jti = secrets.token_hex(16)
    exp = datetime.utcnow() + timedelta(minutes=settings.token_minutes)
    db.add(UserSession(user_id=user.id, jti=jti, expires_at=exp, ip=ip))
    token = jwt.encode(
        {"sub": str(user.id), "cid": user.company_id, "role": user.role, "jti": jti, "exp": exp},
        settings.secret_key, algorithm="HS256",
    )
    return token


@dataclass
class Ctx:
    db: Session
    user: User
    ip: str | None

    @property
    def company_id(self) -> int:
        return self.user.company_id

    def require(self, perm: str) -> None:
        if not has_permission(self.user.role, perm):
            raise HTTPException(403, f"Droit insuffisant ({perm}) pour le profil {self.user.role}.")


bearer = HTTPBearer(auto_error=False)


def get_ctx(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Ctx:
    if creds is None:
        raise HTTPException(401, "Authentification requise.")
    try:
        payload = jwt.decode(creds.credentials, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session invalide ou expirée.")
    sess = db.scalar(select(UserSession).where(UserSession.jti == payload.get("jti")))
    now = datetime.utcnow()
    if not sess or sess.revoked or sess.expires_at < now:
        raise HTTPException(401, "Session expirée.")
    if (now - sess.last_seen) > timedelta(minutes=settings.idle_minutes):
        sess.revoked = True
        db.commit()
        raise HTTPException(401, "Session fermée pour inactivité.")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "Compte désactivé.")
    sess.last_seen = now
    db.commit()
    return Ctx(db=db, user=user, ip=request.client.host if request.client else None)


def need(perm: str):
    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        ctx.require(perm)
        return ctx
    return dep
