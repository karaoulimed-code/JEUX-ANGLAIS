import datetime as dt
import secrets

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User, UserSession
from .permissions import has_permission

bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def check_password_policy(pw: str) -> None:
    if len(pw) < 10 or pw.lower() == pw or pw.upper() == pw or not any(c.isdigit() for c in pw):
        raise HTTPException(400, "Le mot de passe doit contenir au moins 10 caractères, une majuscule, une minuscule et un chiffre.")


def create_session_token(db: Session, user: User, ip: str | None, ua: str | None) -> str:
    s = get_settings()
    sid = secrets.token_hex(24)
    db.add(UserSession(id=sid, user_id=user.id, ip=ip, user_agent=(ua or "")[:300]))
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": str(user.id), "sid": sid, "exp": exp}, s.secret_key, algorithm=ALGO)


def refresh_token(user: User, sid: str) -> str:
    s = get_settings()
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": str(user.id), "sid": sid, "exp": exp}, s.secret_key, algorithm=ALGO)


def get_current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    s = get_settings()
    try:
        payload = jwt.decode(creds.credentials, s.secret_key, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expirée, veuillez vous reconnecter")
    except jwt.PyJWTError:
        raise HTTPException(401, "Jeton invalide")
    sess = db.get(UserSession, payload.get("sid"))
    now = dt.datetime.now(dt.timezone.utc)
    if not sess or sess.revoked_at:
        raise HTTPException(401, "Session fermée")
    if now - sess.last_seen_at > dt.timedelta(minutes=s.session_idle_minutes):
        sess.revoked_at = now
        db.commit()
        raise HTTPException(401, "Session expirée pour inactivité")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "Compte désactivé")
    sess.last_seen_at = now
    db.commit()
    request.state.user = user
    request.state.sid = sess.id
    return user


def require(perm: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Droit insuffisant ({perm})")
        return user
    return dep
