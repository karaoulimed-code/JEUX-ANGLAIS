from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Sequence

PREFIX = {"FACTURE": "FAC", "AVOIR": "AV", "PAYMENT": "REG", "ADJ": "OD", "ENTRY": "ECR"}


def next_number(db: Session, key: str, year: int) -> str:
    """Numérotation chronologique continue, sans trou, par type et par année
    (verrou de ligne : deux utilisateurs ne peuvent pas obtenir le même numéro)."""
    seq = db.execute(select(Sequence).where(Sequence.key == key, Sequence.year == year).with_for_update()).scalar_one_or_none()
    if seq is None:
        seq = Sequence(key=key, year=year, next_value=1)
        db.add(seq)
        db.flush()
    n = seq.next_value
    seq.next_value = n + 1
    return f"{PREFIX.get(key, key)}-{year}-{n:05d}"
