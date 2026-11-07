"""Fixtures de test : base isolée par test (SQLite en mémoire par défaut, PostgreSQL si
AP_TEST_DATABASE_URL est défini), entreprise de test et utilisateurs pour chaque rôle."""
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app import models  # noqa
from app.db import Base, get_db
from app.main import app
from app.models import ExchangeRate, TreasuryAccount, User
from app.security import Ctx, hash_password
from app.seed import create_company, rib_with_key

PWD = "Test2026pass"
ROLES = ["dg", "daf", "resp_achats", "resp_compta", "agent_compta", "tresorier", "lecture"]
TODAY = date.today()


@pytest.fixture()
def engine():
    url = os.getenv("AP_TEST_DATABASE_URL")
    if url:
        eng = create_engine(url)
        Base.metadata.drop_all(eng)
        Base.metadata.create_all(eng)
        yield eng
        Base.metadata.drop_all(eng)
    else:
        eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        with eng.connect() as c:
            c.execute(text("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(eng)
        yield eng


@pytest.fixture()
def db(engine):
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = S()
    yield s
    s.close()


class World:
    """Entreprise de test avec un utilisateur par rôle et des helpers."""

    def __init__(self, db):
        self.db = db
        self.company, admin = create_company(db, "PME Test SARL", "1234567/A/M/000", "admin@t.tn", PWD)
        self.users = {"admin": admin}
        for r in ROLES:
            u = User(company_id=self.company.id, email=f"{r}@t.tn", full_name=r.upper(), role=r,
                     password_hash=hash_password(PWD))
            db.add(u)
            db.flush()
            self.users[r] = u
        # second agent pour tester la séparation des tâches
        u = User(company_id=self.company.id, email="agent2@t.tn", full_name="AGENT2", role="agent_compta",
                 password_hash=hash_password(PWD))
        db.add(u)
        db.flush()
        self.users["agent2"] = u
        self.bank = TreasuryAccount(company_id=self.company.id, name="BNA", account_code="5321",
                                    opening_balance=Decimal("100000.000"))
        db.add(self.bank)
        db.add(ExchangeRate(company_id=self.company.id, currency="EUR", rate_date=TODAY - timedelta(days=400),
                            rate=Decimal("3.300000")))
        db.flush()

    def ctx(self, role) -> Ctx:
        return Ctx(db=self.db, user=self.users[role], ip="test")

    def supplier(self, code="F1", rs_code="RS_ACHATS_1_5", currency="TND", category="regulier", days=30, **kw):
        from app.services import suppliers as s
        sup, _ = s.create_supplier(self.ctx("resp_achats"), {
            "code": code, "legal_name": f"Fournisseur {code}", "tax_id": f"{abs(hash(code)) % 9999999:07d}/A/M/000",
            "rs_code": rs_code, "currency": currency, "category": category, "payment_terms_days": days,
            "is_resident": currency == "TND", **kw}, force=True)
        s.approve_supplier(self.ctx("resp_compta"), sup, "actif")
        acc, _ = s.add_bank_account(self.ctx("resp_achats"), sup, {"bank_name": "B", "currency": currency,
                                                                    "rib": rib_with_key(f"0100{len(code):02d}00000000{sup.id:04d}")})
        s.verify_bank_account(self.ctx("daf"), acc, True, "ok")
        return sup

    def order(self, sup, lines, days_ago=30):
        from app.services import purchasing as p
        po = p.create_order(self.ctx("resp_achats"), {"supplier_id": sup.id, "order_date": TODAY - timedelta(days=days_ago),
                                                      "expected_date": TODAY - timedelta(days=days_ago - 5), "lines": lines})
        p.submit_order(self.ctx("resp_achats"), po)
        p.approve_order(self.ctx("dg"), po, True)
        return po

    def receive(self, po, qtys, days_ago=20, rejected=None):
        from app.services import purchasing as p
        return p.create_receipt(self.ctx("agent2"), {
            "order_id": po.id, "receipt_date": TODAY - timedelta(days=days_ago),
            "lines": [{"order_line_id": l.id, "qty_received": q, "qty_rejected": (rejected or {}).get(i, 0)}
                      for i, (l, q) in enumerate(zip(po.lines, qtys))]})

    def attach(self, inv):
        from app.models import Attachment
        self.db.add(Attachment(company_id=self.company.id, entity="facture", entity_id=inv.id, filename="f.pdf",
                               content_type="application/pdf", size=1, sha256="x" * 64, storage_path="/dev/null"))
        self.db.flush()

    def invoice(self, sup, lines, number="F-1", days_ago=10, order=None, attach=True, **kw):
        from app.services import invoices as i
        inv = i.create_invoice(self.ctx("agent_compta"), {
            "supplier_id": sup.id, "supplier_number": number, "invoice_date": TODAY - timedelta(days=days_ago),
            "order_id": order.id if order else None, "lines": lines, **kw})
        if attach:
            self.attach(inv)
        return inv

    def validate(self, inv, force=False):
        from app.services import invoices as i
        i.submit_invoice(self.ctx("agent_compta"), inv)
        force = force or bool(i.blocking(inv.anomalies))
        approvers = ["resp_compta", "daf", "dg"]
        for lvl in range(inv.required_levels):
            role = approvers[lvl]
            if force and lvl == 0:
                role = "daf"
            if force and lvl == 1:
                role = "dg"
            i.approve_invoice(self.ctx(role), inv, force=force,
                              justification="Validation forcée pour les besoins du test" if force else None)
        return inv

    def pay(self, sup, allocs, days_ago=0, method="virement", **kw):
        from app.services import payments as p
        pay, _ = p.create_payment(self.ctx("tresorier"), {
            "supplier_id": sup.id, "method": method, "treasury_account_id": self.bank.id,
            "payment_date": TODAY - timedelta(days=days_ago),
            "allocations": [{"invoice_id": inv.id, "amount": amt} for inv, amt in allocs], **kw})
        p.submit_payment(self.ctx("tresorier"), pay)
        p.approve_payment(self.ctx("daf"), pay)
        if pay.required_approvals > 1:
            p.approve_payment(self.ctx("dg"), pay)
        p.execute_payment(self.ctx("tresorier"), pay, TODAY - timedelta(days=days_ago))
        return pay


@pytest.fixture()
def w(db):
    return World(db)


def L(desc="Article", q="10", pu="100.000", tva="19", **kw):
    return {"description": desc, "quantity": Decimal(q), "unit_price": Decimal(pu), "tva_rate": Decimal(tva), **kw}


@pytest.fixture()
def client(engine, w):
    w.db.commit()
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        s = S()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
