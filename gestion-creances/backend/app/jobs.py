"""Traitements planifiés (à lancer chaque nuit par cron ou par le service « scheduler »).

    python -m app.jobs nightly
"""
import sys

from .db import SessionLocal
from .services import risk
from .services.ledger import coherence_check
from . import audit


def nightly() -> None:
    db = SessionLocal()
    try:
        res = risk.compute_all(db)
        coh = coherence_check(db)
        audit.log(db, None, "NIGHTLY_JOB", "system", None, {"risk_scored": len(res), "degraded": sum(1 for r in res if r["degraded"]),
                                                            "coherence_ok": coh["ok"], "anomalies": len(coh["anomalies"])})
        db.commit()
        print(f"Notation : {len(res)} clients ; concordance : {'OK' if coh['ok'] else str(len(coh['anomalies'])) + ' anomalie(s)'}")
        if not coh["ok"]:
            sys.exit(2)
    finally:
        db.close()


if __name__ == "__main__":
    {"nightly": nightly}[sys.argv[1] if len(sys.argv) > 1 else "nightly"]()
