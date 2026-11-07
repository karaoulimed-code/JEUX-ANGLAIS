import os

os.environ["GPC_DATABASE_URL"] = os.environ.get("GPC_TEST_DATABASE_URL", "postgresql+psycopg://creances:creances@localhost:5432/creances_test")
os.environ["GPC_STORAGE_DIR"] = "/tmp/gpc_test_storage"

import datetime as dt  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app import seed  # noqa: E402

PW = "Motdepasse2026"
ROLES = ["ADMIN", "DAF", "COMPTABLE", "RECOUVREMENT", "COMMERCIAL", "LECTURE"]


@pytest.fixture(scope="session", autouse=True)
def schema():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as c:
        tables = c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")).scalars().all()
        c.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
    seed.run(PW)
    db = SessionLocal()
    for r in ROLES[1:]:
        db.add(User(username=r.lower(), full_name=f"Utilisateur {r}", role=r, password_hash=hash_password(PW), must_change_password=False))
    db.add(User(username="daf2", full_name="Second DAF", role="DAF", password_hash=hash_password(PW), must_change_password=False))
    db.add(User(username="commercial2", full_name="Commercial 2", role="COMMERCIAL", password_hash=hash_password(PW), must_change_password=False))
    db.commit()
    db.close()
    yield


@pytest.fixture
def client():
    return TestClient(app)


class Api:
    def __init__(self, client, username):
        self.c = client
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PW})
        assert r.status_code == 200, r.text
        self.h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        self.user = r.json()["user"]

    def get(self, url, **kw):
        return self.c.get("/api/v1" + url, headers=self.h, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post("/api/v1" + url, json=json, headers=self.h, **kw)

    def put(self, url, json=None, **kw):
        return self.c.put("/api/v1" + url, json=json, headers=self.h, **kw)

    def delete(self, url):
        return self.c.delete("/api/v1" + url, headers=self.h)

    def ok(self, method, url, json=None, status=(200, 201), **kw):
        r = getattr(self, method)(url, json=json, **kw) if method != "get" and method != "delete" else getattr(self, method)(url, **kw)
        assert r.status_code in status, f"{method} {url} -> {r.status_code} {r.text}"
        return r.json()


@pytest.fixture
def api(client):
    cache = {}

    def get(username="comptable"):
        if username not in cache:
            cache[username] = Api(client, username)
        return cache[username]
    return get


D = Decimal


def mk_customer(a, **kw):
    data = {"legal_name": kw.pop("legal_name", "Client Test SARL"), "payment_terms_days": kw.pop("payment_terms_days", 30), **kw}
    return a.ok("post", "/customers", data)


def mk_invoice(a, customer_id, issue, amount_ht="1000", vat="TVA19", validate=True, installments=None, currency=None,
               exchange_rate=None, doc_type="FACTURE", related=None, stamp=None, due=None):
    body = {"customer_id": customer_id, "issue_date": str(issue), "doc_type": doc_type,
            "lines": [{"description": "Prestation", "quantity": "1", "unit_price": str(amount_ht), "vat_code": vat}]}
    if installments:
        body["installments"] = [{"due_date": str(d), "amount": str(m)} for d, m in installments]
    if currency:
        body["currency"] = currency
    if exchange_rate:
        body["exchange_rate"] = str(exchange_rate)
    if related:
        body["related_invoice_id"] = related
    if stamp is not None:
        body["apply_stamp"] = stamp
    if due:
        body["due_date"] = str(due)
    inv = a.ok("post", "/invoices", body)
    if validate:
        inv = a.ok("post", f"/invoices/{inv['id']}/validate")
    return inv


def method_id(a, code):
    return next(m["id"] for m in a.ok("get", "/payment-methods") if m["code"] == code)
