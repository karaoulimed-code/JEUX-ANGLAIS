"""API de bout en bout : authentification, droits, traçabilité, exports, import, parcours complet."""
import io
from datetime import timedelta

from openpyxl import load_workbook

from app.models import AuditLog
from app.services.common import verify_audit_chain
from tests.conftest import PWD, TODAY, login


def test_login_lockout_and_logout(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "daf@t.tn", "password": "faux"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "daf@t.tn", "password": PWD}).status_code == 423
    h = login(client, "dg@t.tn")
    assert client.get("/api/auth/me", headers=h).json()["role"] == "dg"
    client.post("/api/auth/logout", headers=h)
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert client.get("/api/suppliers").status_code == 401


def test_permissions(client):
    lect = login(client, "lecture@t.tn")
    assert client.get("/api/suppliers", headers=lect).status_code == 200
    r = client.post("/api/suppliers", headers=lect, json={"code": "X", "legal_name": "Xx"})
    assert r.status_code == 403
    admin = login(client, "admin@t.tn")
    assert client.post("/api/invoices/1/approve", headers=admin, json={}).status_code == 403
    assert client.post("/api/payments", headers=login(client, "resp_achats@t.tn"), json={
        "supplier_id": 1, "method": "cheque", "payment_date": str(TODAY)}).status_code == 403
    assert client.get("/api/admin/audit", headers=lect).status_code == 403


def test_full_cycle_through_api(client):
    """Demande → BC → réception → facture → contrôle → validation → paiement → banque → reporting."""
    ach, agent, comp, daf, dg, tres = (login(client, f"{r}@t.tn") for r in
                                       ("resp_achats", "agent_compta", "resp_compta", "daf", "dg", "tresorier"))
    s = client.post("/api/suppliers", headers=ach, json={
        "code": "API1", "legal_name": "Fournisseur API", "tax_id": "7654321/B/M/000", "rs_code": "RS_ACHATS_1_5"}).json()["supplier"]
    assert s["status"] == "en_attente"
    assert client.post(f"/api/suppliers/{s['id']}/status", headers=comp, json={"status": "actif"}).status_code == 200
    acc = client.post(f"/api/suppliers/{s['id']}/bank-accounts", headers=ach,
                      json={"bank_name": "BIAT", "rib": "08008000000000099902"}).json()["compte"]
    assert client.post(f"/api/suppliers/bank-accounts/{acc['id']}/verify", headers=daf,
                       json={"accept": True, "note": "contre-appel"}).status_code == 200
    pr = client.post("/api/purchasing/requests", headers=agent, json={
        "request_date": str(TODAY), "lines": [{"description": "Papier", "quantity": 100, "estimated_unit_price": 12}]}).json()
    client.post(f"/api/purchasing/requests/{pr['id']}/submit", headers=agent)
    assert client.post(f"/api/purchasing/requests/{pr['id']}/decision", headers=daf, json={"approve": True}).status_code == 200
    po = client.post("/api/purchasing/orders", headers=ach, json={
        "supplier_id": s["id"], "request_id": pr["id"], "order_date": str(TODAY - timedelta(days=5)),
        "lines": [{"description": "Papier A4", "quantity": 100, "unit_price": "12.500", "tva_rate": 19}]}).json()
    client.post(f"/api/purchasing/orders/{po['id']}/submit", headers=ach)
    r = client.post(f"/api/purchasing/orders/{po['id']}/decision", headers=dg, json={"approve": True})
    assert r.json()["status"] == "approuvee"
    r = client.post("/api/purchasing/receipts", headers=agent, json={
        "order_id": po["id"], "receipt_date": str(TODAY - timedelta(days=3)),
        "lines": [{"order_line_id": po["lines"][0]["id"], "qty_received": 100}]})
    assert r.status_code == 200, r.text
    inv = client.post("/api/invoices", headers=agent, json={
        "supplier_id": s["id"], "supplier_number": "P-77", "invoice_date": str(TODAY - timedelta(days=2)),
        "order_id": po["id"], "lines": [{"order_line_id": po["lines"][0]["id"], "description": "Papier A4",
                                         "quantity": 100, "unit_price": "12.500", "tva_rate": 19}]}).json()
    assert inv["total_ttc"] == 1488.5 and inv["rs_amount"] == 22.328
    up = client.post("/api/attachments", headers=agent, data={"entity": "facture", "entity_id": inv["id"]},
                     files={"file": ("p77.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert up.status_code == 200, up.text
    r = client.post(f"/api/invoices/{inv['id']}/submit", headers=agent).json()
    assert r["matching_status"] == "conforme", r["anomalies"]
    r = client.post(f"/api/invoices/{inv['id']}/approve", headers=agent, json={})
    assert r.status_code == 403
    r = client.post(f"/api/invoices/{inv['id']}/approve", headers=comp, json={}).json()
    assert r["statut"] == "non_echue"
    pay = client.post("/api/payments", headers=tres, json={
        "supplier_id": s["id"], "method": "virement", "treasury_account_id": 1, "payment_date": str(TODAY),
        "allocations": [{"invoice_id": inv["id"], "amount": "1488.500"}]}).json()["reglement"]
    assert pay["cash_amount"] == 1466.172 and pay["rs_amount"] == 22.328
    client.post(f"/api/payments/{pay['id']}/submit", headers=tres)
    assert client.post(f"/api/payments/{pay['id']}/approve", headers=daf).json()["status"] == "approuve"
    assert client.post(f"/api/payments/{pay['id']}/execute", headers=tres, json={}).json()["status"] == "emis"
    r = client.post("/api/treasury/statements", headers=tres, json={"treasury_account_id": 1, "lines": [
        {"operation_date": str(TODAY), "label": "VIR FOURNISSEUR API", "amount": "-1466.172"}]}).json()
    assert r["rapprochees_auto"] == 1
    assert client.get(f"/api/invoices/{inv['id']}", headers=daf).json()["statut"] == "reglee"
    rec = client.get("/api/accounting/reconciliation", headers=comp).json()
    assert rec["concordant"] and rec["solde_auxiliaire"] == 0
    ret = client.get("/api/reports/export/retenues-source?format=json", headers=comp).json()
    assert ret["lignes"][0]["retenue"] == 22.328
    dash = client.get("/api/reports/dashboard", headers=daf)
    assert dash.status_code == 200
    # traçabilité
    logs = client.get("/api/admin/audit", headers=daf).json()
    assert {"creation", "validation_definitive", "decaissement", "verification_rib"} <= {l["action"] for l in logs}


def test_exports_formats(client, w):
    from decimal import Decimal
    from tests.conftest import L
    s = w.supplier(rs_code=None)
    w.validate(w.invoice(s, [L(q="1", pu="100.000")], days_ago=50))
    w.db.commit()
    h = login(client, "daf@t.tn")
    for name in ("balance-agee", "balance-auxiliaire", "grand-livre", "journal-achats", "journal-reglements",
                 "factures-non-reglees", "factures-litigieuses", "engagements", "avances", "retenues-source",
                 "echeancier", "previsions", "risques"):
        for fmt in ("xlsx", "pdf", "csv"):
            r = client.get(f"/api/reports/export/{name}?format={fmt}", headers=h)
            assert r.status_code == 200, (name, fmt, r.text[:200])
    x = client.get("/api/reports/export/balance-agee?format=xlsx", headers=h)
    ws = load_workbook(io.BytesIO(x.content)).active
    assert ws["A1"].value.startswith("Balance âgée")
    assert client.get("/api/reports/export/balance-agee?format=pdf", headers=h).content[:4] == b"%PDF"
    _ = Decimal


def test_import_csv(client, w):
    w.supplier("IMP", rs_code=None)
    w.db.commit()
    h = login(client, "agent_compta@t.tn")
    csv_ = ("fournisseur;numero;date_facture;montant_ht;taux_tva;timbre\n"
            "IMP;X-1;01/10/2026;100,000;19;1,000\n"
            "INCONNU;X-2;01/10/2026;100;19;\n"
            "IMP;X-3;date;100;19;\n")
    r = client.post("/api/invoices/import", headers=h, files={"file": ("f.csv", csv_.encode(), "text/csv")}).json()
    assert len(r["creees"]) == 1 and len(r["erreurs"]) == 2
    inv = client.get("/api/invoices?q=X-1", headers=h).json()[0]
    assert inv["total_ttc"] == 120.0 and inv["workflow_status"] == "brouillon" and inv["source"] == "import"


def test_ocr_not_enabled_is_explicit(client):
    h = login(client, "agent_compta@t.tn")
    r = client.post("/api/invoices/ocr", headers=h, files={"file": ("f.pdf", b"x", "application/pdf")})
    assert r.status_code == 501


def test_audit_chain_detects_tampering(w):
    from tests.conftest import L
    s = w.supplier(rs_code=None)
    w.validate(w.invoice(s, [L(q="1", pu="100.000")]))
    w.db.flush()
    assert verify_audit_chain(w.db)["integre"]
    log = w.db.query(AuditLog).order_by(AuditLog.id).offset(3).first()
    log.details = {"falsifie": True}
    w.db.flush()
    res = verify_audit_chain(w.db)
    assert not res["integre"] and res["premiere_rupture_id"] == log.id


def test_settings_and_tax_rates_api(client):
    comp = login(client, "resp_compta@t.tn")
    rates = client.get("/api/admin/tax-rates", headers=comp).json()
    assert {"TVA19", "TVA13", "TVA7", "RS_ACHATS_1_5", "TIMBRE_FACTURE"} <= {r["code"] for r in rates}
    assert all(r["to_verify"] for r in rates)
    r = client.put("/api/admin/settings/tolerance_prix_pct", headers=comp, json={"value": "5"})
    assert r.status_code == 200
    r = client.put("/api/admin/settings/tolerance_prix_pct", headers=login(client, "agent_compta@t.tn"), json={"value": "50"})
    assert r.status_code == 403
    r = client.put("/api/admin/accounts/fournisseurs", headers=comp, json={"account_code": "4011"})
    assert r.json()["account_code"] == "4011"


def test_daf_can_cancel_validated_invoice_via_api(client, w):
    from tests.conftest import L
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="100.000")]))
    w.db.commit()
    r = client.post(f"/api/invoices/{inv.id}/cancel", headers=login(client, "daf@t.tn"), json={"reason": "Erreur de fournisseur"})
    assert r.status_code == 200 and r.json()["statut"] == "annulee"
    r = client.post(f"/api/invoices/{inv.id}/cancel", headers=login(client, "tresorier@t.tn"), json={"reason": "xxxx"})
    assert r.status_code == 403
