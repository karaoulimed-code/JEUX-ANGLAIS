import hashlib
import json

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import AuditLog, User, now_utc


def _digest(prev: str | None, ts, user_id, action, entity_type, entity_id, details) -> str:
    import datetime as _dt
    ts_s = ts.astimezone(_dt.timezone.utc).isoformat(timespec='microseconds')
    raw = json.dumps([prev, ts_s, user_id, action, entity_type, entity_id, details],
                     sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def log(db: Session, user: User | None, action: str, entity_type: str, entity_id=None,
        details: dict | None = None, ip: str | None = None) -> None:
    """Ajoute une ligne au journal d'audit, dans la même transaction que l'opération.
    Le verrou consultatif garantit un chaînage strict même en accès concurrent."""
    db.execute(text("SELECT pg_advisory_xact_lock(424242)"))
    prev = db.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar()
    ts = now_utc()
    details = json.loads(json.dumps(details or {}, default=str))
    eid = None if entity_id is None else str(entity_id)
    uid = user.id if user else None
    db.add(AuditLog(ts=ts, user_id=uid, username=user.username if user else "system", action=action,
                    entity_type=entity_type, entity_id=eid, details=details, ip=ip, prev_hash=prev,
                    hash=_digest(prev, ts, uid, action, entity_type, eid, details)))


def verify_chain(db: Session) -> dict:
    prev = None
    count = 0
    for row in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars():
        expected = _digest(prev, row.ts, row.user_id, row.action, row.entity_type, row.entity_id, row.details)
        if row.prev_hash != prev or row.hash != expected:
            return {"ok": False, "broken_at_id": row.id, "checked": count}
        prev = row.hash
        count += 1
    return {"ok": True, "checked": count}
