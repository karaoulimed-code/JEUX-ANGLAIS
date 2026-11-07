"""JEU DE DONNÉES DE DÉMONSTRATION — clairement identifié.

Toutes les sociétés créées portent le préfixe « [DÉMO] » et l'indicateur
is_demo = vrai. Les opérations passent par les mêmes services que la saisie
réelle (numérotation, lettrage, écritures, audit) : aucune donnée n'est
injectée en contournant les règles.

    python -m app.demo            # crée les données
Ne jamais exécuter sur une base de production.
"""
import datetime as dt
import random
import sys
from decimal import Decimal

from sqlalchemy import select

from .db import SessionLocal
from .models import Customer, DunningLevel, ExchangeRate, Invoice, PaymentMethod, User
from .security import hash_password
from .services import dunning, invoices, payments, risk
from . import audit

PROFILES = [
    # nom, ville, secteur, délai, plafond, retard moyen, dispersion, part de rejets
    ("[DÉMO] Société Méditerranéenne de Distribution", "Tunis", "COMMERCE", 60, 250000, 5, 8, 0.0),
    ("[DÉMO] Atlas Industries SA", "Sfax", "INDUSTRIE", 90, 400000, 25, 15, 0.0),
    ("[DÉMO] Carthage BTP SARL", "Ben Arous", "BTP", 60, 150000, 70, 40, 0.15),
    ("[DÉMO] Clinique Les Oliviers", "Sousse", "SANTE", 30, 80000, 10, 10, 0.0),
    ("[DÉMO] Hôtel Jasmin Resort", "Nabeul", "TOURISME", 45, 120000, 45, 30, 0.05),
    ("[DÉMO] Office Régional des Services", "Monastir", "PUBLIC", 60, 0, 110, 50, 0.0),
    ("[DÉMO] Sahel Agro Export", "Mahdia", "AGRO", 30, 60000, 0, 5, 0.0),
    ("[DÉMO] Nour Informatique SUARL", "Ariana", "TIC", 30, 30000, 35, 25, 0.10),
    ("[DÉMO] Transports Bizerte Logistique", "Bizerte", "TRANSPORT", 60, 90000, 150, 60, 0.2),
    ("[DÉMO] Euro Textile Partners (EUR)", "Monastir", "INDUSTRIE", 60, 200000, 15, 10, 0.0),
]


def run(seed: int = 2026) -> None:
    rnd = random.Random(seed)
    db = SessionLocal()
    try:
        if db.execute(select(Customer).where(Customer.is_demo.is_(True))).first():
            print("Données de démonstration déjà présentes.")
            return
        today = dt.date.today()
        users = {}
        for un, fn, role in [("demo.daf", "Leïla DAF (démo)", "DAF"), ("demo.compta", "Sami Comptable (démo)", "COMPTABLE"),
                             ("demo.recouv", "Amira Recouvrement (démo)", "RECOUVREMENT"), ("demo.commercial", "Karim Commercial (démo)", "COMMERCIAL")]:
            u = db.execute(select(User).where(User.username == un)).scalar_one_or_none()
            if not u:
                u = User(username=un, full_name=fn, role=role, password_hash=hash_password("Demo2026!x"), must_change_password=False)
                db.add(u)
                db.flush()
            users[role] = u
        compta = users["COMPTABLE"]
        for i in range(0, 430, 7):  # cours EUR fictifs de démonstration
            db.add(ExchangeRate(currency="EUR", date=today - dt.timedelta(days=i), rate=Decimal("3.35") + Decimal(rnd.randint(-8, 8)) / 100,
                                source="DÉMO – cours fictif"))
        db.flush()
        methods = {m.code: m for m in db.execute(select(PaymentMethod)).scalars()}
        for idx, (name, city, sector, terms, limit, delay, disp, rej) in enumerate(PROFILES, 1):
            cur = "EUR" if "(EUR)" in name else "TND"
            c = Customer(code=f"DEMO{idx:03d}", legal_name=name, city=city, sector_code=sector, zone_code=city.upper().replace(" ", "_"),
                         category_code="ADM" if sector == "PUBLIC" else ("EXPORT" if cur == "EUR" else "PME"),
                         tax_id=f"{1000000 + idx * 7919}X/A/M/000", payment_terms_days=terms, credit_limit=Decimal(limit),
                         max_exposure=Decimal(limit) * Decimal("1.3"), currency=cur, contact_name="Madame, Monsieur",
                         salesperson_id=users["COMMERCIAL"].id if idx % 3 == 0 else None, is_demo=True,
                         notes="Client fictif du jeu de démonstration")
            db.add(c)
            db.flush()
            d = today - dt.timedelta(days=420)
            while d < today - dt.timedelta(days=2):
                d += dt.timedelta(days=rnd.randint(12, 35))
                if d >= today:
                    break
                amount = Decimal(rnd.randint(800, 25000)) if cur == "TND" else Decimal(rnd.randint(2000, 15000))
                data = {"customer_id": c.id, "issue_date": d, "currency": cur, "apply_stamp": cur == "TND",
                        "lines": [{"description": "Fourniture / prestation (démo)", "quantity": 1, "unit_price": amount,
                                   "vat_code": "TVA0" if cur == "EUR" else rnd.choice(["TVA19", "TVA19", "TVA7"])}]}
                inv = invoices.save_draft(db, compta, data)
                inv.is_demo = True
                invoices.validate(db, compta, inv)
                pay_day = inv.due_date + dt.timedelta(days=max(-10, int(rnd.gauss(delay, disp))))
                if pay_day >= today:
                    continue
                kind = rnd.choice(["VIR", "VIR", "CHQ", "CHQ", "EFF"]) if cur == "TND" else "VIR"
                partial = rnd.random() < 0.15
                amt = (inv.total_ttc * Decimal("0.5")).quantize(Decimal("0.001")) if partial else inv.total_ttc
                body = {"customer_id": c.id, "method_id": methods[kind].id, "receipt_date": pay_day, "amount": amt, "currency": cur,
                        "reference": f"{kind}{rnd.randint(100000, 999999)}" if kind != "VIR" else None,
                        "bank_name": rnd.choice(["BIAT", "STB", "BNA", "Attijari", "Amen Bank", "UIB"]),
                        "value_date": pay_day + dt.timedelta(days=30) if kind == "EFF" else None,
                        "allocations": [{"invoice_id": inv.id, "amount": amt}]}
                p, _ = payments.create_payment(db, compta, body)
                if kind in ("CHQ", "EFF"):
                    if rnd.random() < rej and pay_day + dt.timedelta(days=5) < today:
                        payments.change_status(db, compta, p, "REJETE", pay_day + dt.timedelta(days=5), "Provision insuffisante (démo)")
                    elif (p.value_date or pay_day) + dt.timedelta(days=3) < today:
                        clear = max(pay_day + dt.timedelta(days=3), p.value_date or pay_day)
                        if kind == "EFF":
                            payments.change_status(db, compta, p, "REMIS", pay_day + dt.timedelta(days=2), None)
                        payments.change_status(db, compta, p, "ENCAISSE", clear, None)
            db.flush()
        # Un litige et une relance pour illustrer le recouvrement
        btp = db.execute(select(Customer).where(Customer.code == "DEMO003")).scalar_one()
        old = db.execute(select(Invoice).where(Invoice.customer_id == btp.id, Invoice.balance > 0).order_by(Invoice.due_date)).scalars().first()
        if old:
            invoices.classify(db, compta, old, "LITIGIEUSE", "Contestation de la qualité des travaux du lot 3 (démo)")
        lv = db.execute(select(DunningLevel).where(DunningLevel.level == 1)).scalar_one()
        props = dunning.proposals(db, today)
        for pr in props["overdue"][:4]:
            dunning.create_action(db, users["RECOUVREMENT"], {
                "customer_id": pr["customer_id"], "level_id": lv.id, "action_type": "RELANCE_1", "channel": "EMAIL",
                "action_date": today - dt.timedelta(days=5), "invoice_ids": [i["invoice_id"] for i in pr["invoices"]],
                "result_code": "SANS_REPONSE", "next_action_date": today, "next_action": "Appel téléphonique",
                "comments": "Relance de démonstration"})
        risk.compute_all(db, today)
        audit.log(db, None, "DEMO_DATA_LOADED", "system", None, {"customers": len(PROFILES)})
        db.commit()
        print("Jeu de démonstration créé. Comptes : demo.daf / demo.compta / demo.recouv / demo.commercial — mot de passe Demo2026!x")
    finally:
        db.close()


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        print("Ce script crée des données FICTIVES. Relancez avec --yes pour confirmer (jamais en production).")
        sys.exit(1)
    run()
