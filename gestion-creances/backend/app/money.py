"""Arithmétique monétaire exacte : jamais de float pour les montants.

Le dinar tunisien se divise en 1 000 millimes : tous les montants sont
arrondis à 3 décimales (arrondi bancaire « au plus proche, 0,5 vers le haut »).
"""
from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0.000")
Q3 = Decimal("0.001")
Q6 = Decimal("0.000001")


def D(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q3(value) -> Decimal:
    return D(value).quantize(Q3, rounding=ROUND_HALF_UP)


def q6(value) -> Decimal:
    return D(value).quantize(Q6, rounding=ROUND_HALF_UP)
