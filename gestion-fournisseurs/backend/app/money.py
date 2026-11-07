"""Arithmétique monétaire exacte (Decimal, 3 décimales, arrondi commercial)."""
from decimal import ROUND_HALF_UP, Decimal

Q3 = Decimal("0.001")
Q6 = Decimal("0.000001")
ZERO = Decimal("0")


def D(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def r3(value) -> Decimal:
    return D(value).quantize(Q3, rounding=ROUND_HALF_UP)


def r6(value) -> Decimal:
    return D(value).quantize(Q6, rounding=ROUND_HALF_UP)


def pct(base, rate_pct) -> Decimal:
    return r3(D(base) * D(rate_pct) / Decimal(100))
