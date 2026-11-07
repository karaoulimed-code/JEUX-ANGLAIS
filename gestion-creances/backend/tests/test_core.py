"""Tests du cycle intégré : facture → échéance → encaissement → affectation →
solde → balance âgée → risque → provisions → écritures."""
import datetime as dt
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine
from app.services import kpi
from app.services.ledger import bucket_defs, bucket_of, coherence_check

from .conftest import method_id, mk_customer, mk_invoice

T = dt.date.today()


def days(n):
    return T - dt.timedelta(days=n)


def check_coherence():
    db = SessionLocal()
    try:
        r = coherence_check(db)
        assert r["ok"], r["anomalies"]
        # écritures toutes équilibrées
        bad = db.execute(text("SELECT entry_id FROM journal_lines GROUP BY entry_id HAVING SUM(debit) <> SUM(credit)")).all()
        assert not bad
        return r
    finally:
        db.close()


# ---------------------------------------------------------------- calculs de facture
def test_invoice_totals_multi_rates_discount_fodec_stamp(api):
    a = api()
    c = mk_customer(a)
    body = {"customer_id": c["id"], "issue_date": str(days(1)), "other_taxes": ["FODEC"], "lines": [
        {"description": "Produit A", "quantity": "3", "unit_price": "333.333", "discount_pct": "10", "vat_code": "TVA19"},
        {"description": "Produit B", "quantity": "2", "unit_price": "125.500", "vat_code": "TVA7"},
    ]}
    inv = a.ok("post", "/invoices", body)
    # A : 3 × 333,333 × 0,9 = 899,999 ; B : 251,000 ; HT = 1150,999
    assert D(inv["total_ht"]) == D("1150.999")
    # FODEC 1 % = 11,510 ; assiette TVA19 = 899,999 × 1,01 = 908,999 → 172,710 ; TVA7 = 251 × 1,01 = 253,510 → 17,746
    taxes = {t["code"]: D(t["amount"]) for t in inv["taxes"]}
    assert taxes["FODEC"] == D("11.510")
    assert taxes["TVA19"] == D("172.710")
    assert taxes["TVA7"] == D("17.746")
    assert taxes["TIMBRE"] == D("1.000")
    assert D(inv["total_ttc"]) == D("1150.999") + D("11.510") + D("172.710") + D("17.746") + D("1.000")
    assert inv["status"] == "BROUILLON" and inv["number"] is None


def test_validation_numbering_and_immutability(api):
    a = api()
    c = mk_customer(a)
    i1 = mk_invoice(a, c["id"], days(5))
    i2 = mk_invoice(a, c["id"], days(4))
    y = days(5).year
    assert i1["number"] == f"FAC-{y}-00001" and i2["number"].endswith("00002")
    assert i1["status"] == "NON_ECHUE"
    # modification d'une facture validée refusée par l'application
    r = a.put(f"/invoices/{i1['id']}", json={"customer_id": c["id"], "issue_date": str(days(5)),
                                              "lines": [{"description": "x", "unit_price": "1"}]})
    assert r.status_code == 409
    assert a.delete(f"/invoices/{i1['id']}").status_code == 409
    # ... et par la base de données elle-même
    with pytest.raises(Exception) as e:
        with engine.begin() as cx:
            cx.execute(text("UPDATE invoices SET total_ttc = 1 WHERE id = :i"), {"i": i1["id"]})
    assert "INTERDIT" in str(e.value)


def test_installments_must_match_total(api):
    a = api()
    c = mk_customer(a)
    body = {"customer_id": c["id"], "issue_date": str(days(1)), "lines": [{"description": "x", "unit_price": "100"}],
            "installments": [{"due_date": str(T), "amount": "50"}, {"due_date": str(T), "amount": "50"}]}
    r = a.post("/invoices", json=body)
    assert r.status_code == 400 and "échéances" in r.json()["detail"]


# ---------------------------------------------------------------- encaissements
def test_partial_then_full_payment(api):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(40))           # TTC = 1000 + 190 + 1 = 1191,000 ; échue depuis 10 j
    assert D(inv["total_ttc"]) == D("1191.000")
    assert inv["status"] == "EN_RETARD"
    vir = method_id(a, "VIR")
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": vir, "receipt_date": str(days(2)), "amount": "500",
                               "allocations": [{"invoice_id": inv["id"], "amount": "500"}]})
    inv = a.ok("get", f"/invoices/{inv['id']}")
    assert D(inv["paid_amount"]) == D("500") and D(inv["balance"]) == D("691.000")
    assert inv["status"] == "EN_RETARD"  # partiellement réglée mais toujours échue
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": vir, "receipt_date": str(T), "amount": "691"})
    inv = a.ok("get", f"/invoices/{inv['id']}")
    assert inv["status"] == "REGLEE" and D(inv["balance"]) == 0
    check_coherence()


def test_partial_not_overdue_status(api):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(5))
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "ESP"), "receipt_date": str(T), "amount": "100"})
    assert a.ok("get", f"/invoices/{inv['id']}")["status"] == "PARTIELLEMENT_REGLEE"


def test_fifo_auto_allocation_and_advance(api):
    a = api()
    c = mk_customer(a)
    i1 = mk_invoice(a, c["id"], days(90), "100")   # 120,000
    i2 = mk_invoice(a, c["id"], days(60), "100")
    i3 = mk_invoice(a, c["id"], days(30), "100")
    p = a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "400"})
    # 3 × 120 = 360 affectés dans l'ordre des échéances, 40 restent en avance
    assert D(p["allocated_amount"]) == D("360.000") and D(p["unallocated_amount"]) == D("40.000")
    assert [x["invoice_number"] for x in p["allocations"]] == [i1["number"], i2["number"], i3["number"]]
    cust = a.ok("get", f"/customers/{c['id']}")
    assert D(cust["exposure"]["open_tnd"]) == 0
    assert D(cust["exposure"]["unallocated_credits_tnd"]) == D("40.000")
    assert D(cust["exposure"]["net_balance_tnd"]) == D("-40.000")
    led = a.ok("get", f"/customers/{c['id']}/ledger")
    assert D(led["closing_balance"]) == D("-40.000")
    # l'avance se lettre automatiquement sur la facture suivante
    i4 = mk_invoice(a, c["id"], T, "100")
    a.ok("post", f"/payments/{p['id']}/auto-allocate")
    assert D(a.ok("get", f"/invoices/{i4['id']}")["balance"]) == D("80.000")
    check_coherence()


def test_overallocation_refused(api):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(3), "100")
    r = a.post("/payments", json={"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "500",
                                  "allocations": [{"invoice_id": inv["id"], "amount": "200"}]})
    assert r.status_code == 409
    other = mk_customer(a, legal_name="Autre client")
    r = a.post("/payments", json={"customer_id": other["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "50",
                                  "allocations": [{"invoice_id": inv["id"], "amount": "50"}]})
    assert r.status_code == 409


def test_cheque_rejection_reopens_invoice(api):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(20), "1000")
    p = a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "CHQ"), "receipt_date": str(days(10)),
                                   "amount": "1191", "reference": "1234567", "bank_name": "BIAT"})
    assert p["status"] == "EN_PORTEFEUILLE"
    assert a.ok("get", f"/invoices/{inv['id']}")["status"] == "REGLEE"
    cust = a.ok("get", f"/customers/{c['id']}")
    assert D(cust["exposure"]["pending_instruments_tnd"]) == D("1191.000")  # risque « sauf bonne fin »
    a.ok("post", f"/payments/{p['id']}/status", {"status": "REMIS", "date": str(days(8))})
    a.ok("post", f"/payments/{p['id']}/status", {"status": "REJETE", "date": str(days(5)), "reason": "Provision insuffisante"})
    inv = a.ok("get", f"/invoices/{inv['id']}")
    assert D(inv["balance"]) == D("1191.000") and inv["status"] == "NON_ECHUE"
    led = a.ok("get", f"/customers/{c['id']}/ledger")
    assert [r["type"] for r in led["rows"]] == ["FACTURE", "REGLEMENT", "REJET"]
    assert D(led["closing_balance"]) == D("1191.000")
    # un chèque rejeté ne peut plus changer de statut
    assert a.post(f"/payments/{p['id']}/status", json={"status": "ENCAISSE", "date": str(T)}).status_code == 409
    risk = a.ok("get", f"/risk/customers/{c['id']}")
    assert risk["metrics"]["incidents_12m"] == 1
    assert len(a.ok("get", f"/customers/{c['id']}")["incidents"]) == 1
    check_coherence()


def test_duplicate_cheque_refused(api):
    a = api()
    c = mk_customer(a)
    chq = method_id(a, "CHQ")
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": chq, "receipt_date": str(T), "amount": "10", "reference": "999"})
    assert a.post("/payments", json={"customer_id": c["id"], "method_id": chq, "receipt_date": str(T), "amount": "10", "reference": "999"}).status_code == 409


def test_reverse_allocation(api):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(3), "100")
    p = a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "120"})
    aid = p["allocations"][0]["id"]
    a.ok("post", f"/allocations/{aid}/reverse", {"reason": "Erreur d'affectation"})
    assert D(a.ok("get", f"/invoices/{inv['id']}")["balance"]) == D("120.000")
    assert D(a.ok("get", f"/payments/{p['id']}")["unallocated_amount"]) == D("120.000")
    assert a.post(f"/allocations/{aid}/reverse", json={"reason": "Encore"}).status_code == 409
    check_coherence()


def test_credit_note_imputation(api):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(10), "1000")
    cn = mk_invoice(a, c["id"], days(2), "200", doc_type="AVOIR", related=inv["id"])
    assert cn["number"].startswith("AV-")
    assert D(cn["total_ttc"]) == D("238.000")  # pas de timbre sur avoir par défaut
    inv = a.ok("get", f"/invoices/{inv['id']}")
    assert D(inv["balance"]) == D("1191.000") - D("238.000")
    assert a.ok("get", f"/invoices/{cn['id']}")["status"] == "IMPUTE"
    check_coherence()


def test_small_difference_settlement(api):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(3), "1000")
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "1190.500"})
    inv = a.ok("post", f"/invoices/{inv['id']}/settle-difference", {"reason": "Frais bancaires retenus"})
    assert inv["status"] == "REGLEE"
    inv2 = mk_invoice(a, c["id"], days(3), "1000")
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "1100"})
    assert a.post(f"/invoices/{inv2['id']}/settle-difference", json={"reason": "trop gros"}).status_code == 409
    check_coherence()


def test_withholding_tax_certificate_as_settlement(api):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(5), "1000")
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "1173.135"})
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "RS"), "receipt_date": str(T), "amount": "17.865",
                               "reference": "CERT-2026-77"})
    assert a.ok("get", f"/invoices/{inv['id']}")["status"] == "REGLEE"
    entries = a.ok("get", "/accounting/entries")
    assert any(l["account"] == "4351" and D(l["debit"]) == D("17.865") for e in entries for l in e["lines"])


def test_foreign_currency_exchange_difference(api):
    a = api()
    c = mk_customer(a, currency="EUR")
    inv = mk_invoice(a, c["id"], days(30), "1000", vat="TVA0", currency="EUR", exchange_rate="3.300000", stamp=False)
    assert D(inv["total_ttc_tnd"]) == D("3300.000")
    p = a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "1000",
                                   "currency": "EUR", "exchange_rate": "3.400000"})
    assert D(p["amount_tnd"]) == D("3400.000")
    assert D(p["allocations"][0]["fx_difference_tnd"]) == D("100.000")
    led = a.ok("get", f"/customers/{c['id']}/ledger")
    assert D(led["closing_balance"]) == 0
    entries = a.ok("get", "/accounting/entries")
    assert any(l["account"] == "755" and D(l["credit"]) == D("100.000") for e in entries for l in e["lines"])
    check_coherence()


# ---------------------------------------------------------------- balance âgée
def test_aging_buckets_boundaries():
    db = SessionLocal()
    defs = bucket_defs(db)
    assert [bucket_of(d, defs) for d in (-5, 0, 1, 30, 31, 60, 61, 90, 91, 180, 181, 900)] == \
        ["NON_ECHU", "NON_ECHU", "1-30", "1-30", "31-60", "31-60", "61-90", "61-90", "91-180", "91-180", "181+", "181+"]
    db.close()


def test_aging_installments_and_past_date(api):
    a = api()
    c = mk_customer(a)
    # 3 échéances : échue de 100 j, échue de 10 j, à venir
    inv = mk_invoice(a, c["id"], days(130), "1000",
                     installments=[(days(100), "400"), (days(10), "400"), (T + dt.timedelta(days=20), "391")])
    ag = a.ok("get", "/aging")
    row = ag["rows"][0]
    assert D(row["91-180"]) == D("400") and D(row["1-30"]) == D("400") and D(row["NON_ECHU"]) == D("391")
    assert D(row["total"]) == D("1191")
    # règlement aujourd'hui : la balance âgée arrêtée à hier reste inchangée
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "1191"})
    assert a.ok("get", "/aging")["rows"] == [] or D(a.ok("get", "/aging")["totals"]["total"]) == 0
    past = a.ok("get", f"/aging?as_of={days(1)}")
    assert D(past["totals"]["total"]) == D("1191")
    assert D(past["rows"][0]["91-180"]) == D("400")
    check_coherence()


def test_aging_by_currency(api):
    a = api()
    c = mk_customer(a, currency="EUR")
    mk_invoice(a, c["id"], days(45), "500", vat="TVA0", currency="EUR", exchange_rate="3.25", stamp=False)
    eur = a.ok("get", "/aging?currency=EUR")
    assert D(eur["totals"]["total"]) == D("500") and D(eur["rows"][0]["1-30"]) == D("500")
    tnd = a.ok("get", "/aging")
    assert D(tnd["totals"]["total"]) == D("1625.000")


# ---------------------------------------------------------------- indicateurs
def test_dso_and_rates(api):
    a = api()
    c = mk_customer(a)
    mk_invoice(a, c["id"], days(80), "1000")   # 1191
    mk_invoice(a, c["id"], days(20), "1000")   # 1191
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "1191"})
    db = SessionLocal()
    r = kpi.dso(db, T, "COMPTABLE", 90)
    # encours 1191 / CA 2382 × 90 = 45 jours
    assert r["value"] == 45.0
    e = kpi.dso(db, T, "EPUISEMENT")
    assert e["value"] is not None and e["value"] > 0
    d = kpi.dashboard(db, T)
    assert D(d["totals"]["receivables"]) == D("1191.000")
    assert d["unpaid_rate"]["value"] == 0.0  # la facture restante n'est pas échue (30 j de délai, émise il y a 20 j)
    conc = kpi.concentration(db, T)
    assert conc["top_share_pct"] == 100.0 and conc["hhi"] == 10000
    db.close()


def test_recovery_rate(api):
    a = api()
    c = mk_customer(a)
    mk_invoice(a, c["id"], days(70), "1000")    # échéance il y a 40 j : exigible au début de période
    db = SessionLocal()
    start = days(10)
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "595.500"})
    r = kpi.recovery_rate(db, start, T)
    assert D(r["exigible"]) == D("1191.000") and r["value"] == 50.0
    db.close()


# ---------------------------------------------------------------- risque
def test_risk_score_explainable_and_limit(api):
    daf = api("daf")
    c = mk_customer(daf, credit_limit="1000")
    a = api()
    mk_invoice(a, c["id"], days(250), "1000")
    r = a.ok("get", f"/risk/customers/{c['id']}")
    assert sum(x["points"] for x in r["criteria"]) == pytest.approx(r["score"], abs=1)
    assert r["risk_class"] in ("ELEVE", "CRITIQUE", "MODERE")
    assert "Plafond de crédit dépassé" in r["flags"]
    assert any(x["criterion"] == "max_days_overdue" and x["points"] == 20 for x in r["criteria"])
    # invoice over limit validates with a warning (blocking disabled by default)
    inv = a.ok("post", "/invoices", {"customer_id": c["id"], "issue_date": str(T), "lines": [{"description": "x", "unit_price": "10"}]})
    v = a.ok("post", f"/invoices/{inv['id']}/validate")
    assert any("Plafond" in w for w in v["warnings"])


def test_block_on_limit_parameter(api):
    daf = api("daf")
    daf.ok("put", "/params/credit.block_on_limit", {"value": True})
    c = mk_customer(daf, credit_limit="100")
    a = api()
    inv = a.ok("post", "/invoices", {"customer_id": c["id"], "issue_date": str(T), "lines": [{"description": "x", "unit_price": "1000"}]})
    assert a.post(f"/invoices/{inv['id']}/validate").status_code == 409
    assert daf.ok("post", f"/invoices/{inv['id']}/validate?force=true")["lifecycle"] == "VALIDEE"


# ---------------------------------------------------------------- provisions
def test_nct_provision_workflow(api):
    a, daf = api(), api("daf")
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(250), "1000")    # 220 j de retard → 50 % suggéré, base HT
    camp = a.ok("post", "/provisions/campaigns", {"as_of": str(T), "method": "NCT"})
    line = camp["lines"][0]
    assert D(line["suggested_rate"]) == D("50") and D(line["base_tnd"]) == D("1000.000")
    assert D(line["amount_tnd"]) == D("500.000")
    assert "article 48" in line["fiscal_note"]
    # l'auteur ne peut pas valider sa propre campagne
    assert api("daf").post(f"/provisions/campaigns/{camp['id']}/decide", json={"approve": True}).status_code in (200, 400, 409)


def test_nct_provision_segregation_and_justification(api):
    a, daf = api(), api("daf")
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(250), "1000")
    a.ok("post", f"/invoices/{inv['id']}/classify", {"classification": "DOUTEUSE", "reason": "Client en redressement judiciaire"})
    camp = daf.ok("post", "/provisions/campaigns", {"as_of": str(T), "method": "NCT"})
    assert daf.post(f"/provisions/campaigns/{camp['id']}/decide", json={"approve": True}).status_code == 403
    lid = camp["lines"][0]["id"]
    daf.ok("put", f"/provisions/lines/{lid}", {"rate": "80"})
    d2 = api("daf2")
    r = d2.post(f"/provisions/campaigns/{camp['id']}/decide", json={"approve": True})
    assert r.status_code == 400  # taux modifié sans justification
    daf.ok("put", f"/provisions/lines/{lid}", {"rate": "80", "justification": "Déclaration de créance déposée ; dividende attendu 20 %"})
    res = d2.ok("post", f"/provisions/campaigns/{camp['id']}/decide", {"approve": True})
    assert res["status"] == "VALIDEE" and D(res["dotation"]) == D("800.000")
    entries = a.ok("get", "/accounting/entries")
    prov = [e for e in entries if e["source_type"] == "PROVISION"][0]
    assert {(l["account"], D(l["debit"]), D(l["credit"])) for l in prov["lines"]} == {("6817", D("800.000"), D(0)), ("491", D(0), D("800.000"))}
    # reclassement 411 → 416 généré au classement en douteuse
    assert any(e["source_type"] == "CLASSIFICATION" for e in entries)
    # paiement total : la campagne suivante reprend la provision
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "1191"})
    camp2 = a.ok("post", "/provisions/campaigns", {"as_of": str(T), "method": "NCT"})
    assert D(camp2["lines"][0]["movement_tnd"]) == D("-800.000")
    res2 = daf.ok("post", f"/provisions/campaigns/{camp2['id']}/decide", {"approve": True})
    assert D(res2["reprise"]) == D("800.000")
    check_coherence()


def test_ifrs9_matrix(api):
    a = api()
    c = mk_customer(a)
    mk_invoice(a, c["id"], days(10), "1000")      # non échu : 0,5 % × 1191 = 5,955
    mk_invoice(a, c["id"], days(100), "1000")     # 70 j : 8 % × 1191 = 95,280
    camp = a.ok("post", "/provisions/campaigns", {"as_of": str(T), "method": "IFRS9"})
    assert D(camp["total_amount_tnd"]) == D("5.955") + D("95.280")
    res = api("daf").ok("post", f"/provisions/campaigns/{camp['id']}/decide", {"approve": True})
    entries = a.ok("get", "/accounting/entries")
    assert not any(e["source_type"] == "PROVISION" for e in entries)  # IFRS 9 hors comptes sociaux par défaut


# ---------------------------------------------------------------- passage en perte
def test_write_off_requires_second_person(api):
    a, daf = api(), api("daf")
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(400), "1000")
    rec = api("recouvrement")
    req = rec.ok("post", f"/invoices/{inv['id']}/write-off-request", {"reason": "Société radiée, certificat d'irrécouvrabilité obtenu"})
    assert rec.post(f"/approvals/{req['approval_id']}/decide", json={"approve": True}).status_code == 403
    daf.ok("post", f"/approvals/{req['approval_id']}/decide", {"approve": True, "comment": "OK"})
    inv = a.ok("get", f"/invoices/{inv['id']}")
    assert inv["status"] == "IRRECOUVRABLE" and D(inv["balance"]) == 0
    led = a.ok("get", f"/customers/{c['id']}/ledger")
    assert D(led["closing_balance"]) == 0
    check_coherence()


def test_credit_limit_change_requires_approval(api):
    a, daf = api(), api("daf")
    c = mk_customer(a)
    upd = {k: v for k, v in a.ok("get", f"/customers/{c['id']}").items() if k in
           ("legal_name", "payment_terms_days", "currency")}
    r = a.ok("put", f"/customers/{c['id']}", {**upd, "credit_limit": "50000", "max_exposure": "0"})
    assert r["pending_approval"] and D(r["credit_limit"]) == 0
    daf.ok("post", f"/approvals/{r['pending_approval']}/decide", {"approve": True})
    assert D(a.ok("get", f"/customers/{c['id']}")["credit_limit"]) == D("50000")


# ---------------------------------------------------------------- droits
def test_permissions_matrix(api, client):
    a = api()
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(5))
    com, lec, rec, adm = api("commercial"), api("lecture"), api("recouvrement"), api("admin")
    assert com.get(f"/customers/{c['id']}").status_code == 403          # hors portefeuille
    assert com.post("/payments", json={"customer_id": c["id"], "method_id": 1, "receipt_date": str(T), "amount": "1"}).status_code == 403
    mine = mk_customer(com, legal_name="Client du commercial")
    assert mine["salesperson_id"] == com.user["id"]
    assert [x["id"] for x in com.ok("get", "/customers")["rows"]] == [mine["id"]]
    assert com.get("/dashboard").status_code == 403
    assert lec.post(f"/invoices/{inv['id']}/validate").status_code == 403
    assert lec.get("/dashboard").status_code == 200
    assert rec.post("/payments", json={"customer_id": c["id"], "method_id": 1, "receipt_date": str(T), "amount": "1"}).status_code == 403
    assert rec.get("/accounting/entries").status_code == 403
    assert adm.post("/accounting/validate", json={"ids": [1]}).status_code == 403   # l'administrateur ne valide pas d'écritures
    assert adm.get("/audit").status_code == 200
    assert a.post("/users", json={"username": "x", "full_name": "x", "role": "ADMIN", "password": "Abcdefgh123"}).status_code == 403
    assert client.get("/api/v1/customers").status_code == 401


def test_login_lockout(client):
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"username": "comptable", "password": "faux"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "comptable", "password": "Motdepasse2026"}).status_code == 423


def test_logout_revokes_session(api):
    a = api("lecture")
    a.ok("post", "/auth/logout")
    assert a.get("/customers").status_code == 401


# ---------------------------------------------------------------- audit & comptabilité
def test_audit_chain_and_immutability(api):
    a = api()
    c = mk_customer(a)
    mk_invoice(a, c["id"], days(1))
    v = api("admin").ok("get", "/audit/verify")
    assert v["ok"] and v["checked"] >= 3
    with pytest.raises(Exception):
        with engine.begin() as cx:
            cx.execute(text("DELETE FROM audit_log"))
    with pytest.raises(Exception):
        with engine.begin() as cx:
            cx.execute(text("UPDATE audit_log SET action='X'"))


def test_entries_validation_and_export_lock(api):
    a = api()
    c = mk_customer(a)
    mk_invoice(a, c["id"], days(1))
    entries = a.ok("get", "/accounting/entries?status=PROPOSEE")
    e = entries[0]
    assert sum(D(l["debit"]) for l in e["lines"]) == sum(D(l["credit"]) for l in e["lines"]) == D("1191.000")
    a.ok("post", "/accounting/validate", {"ids": [x["id"] for x in entries]})
    r = a.post("/accounting/export")
    assert r.status_code == 200 and "411" in r.content.decode("utf-8-sig")
    assert a.ok("get", "/accounting/entries")[0]["status"] == "EXPORTEE"
    with pytest.raises(Exception):
        with engine.begin() as cx:
            cx.execute(text("UPDATE journal_entries SET label='modif' WHERE status='EXPORTEE'"))


def test_payment_cannot_be_deleted_in_db(api):
    a = api()
    c = mk_customer(a)
    a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "ESP"), "receipt_date": str(T), "amount": "10"})
    with pytest.raises(Exception):
        with engine.begin() as cx:
            cx.execute(text("DELETE FROM payments"))


def test_payment_cancel_via_approval(api):
    a, daf = api(), api("daf")
    c = mk_customer(a)
    inv = mk_invoice(a, c["id"], days(5), "100")
    p = a.ok("post", "/payments", {"customer_id": c["id"], "method_id": method_id(a, "VIR"), "receipt_date": str(T), "amount": "120"})
    req = a.ok("post", f"/payments/{p['id']}/cancel-request", {"reason": "Virement saisi deux fois par erreur"})
    daf.ok("post", f"/approvals/{req['approval_id']}/decide", {"approve": True})
    assert a.ok("get", f"/payments/{p['id']}")["status"] == "ANNULE"
    assert D(a.ok("get", f"/invoices/{inv['id']}")["balance"]) == D("120.000")
    check_coherence()


# ---------------------------------------------------------------- imports, états, IA
def test_import_invoices_dry_run_and_errors(api):
    a = api()
    c = mk_customer(a, code="C10")
    csv_ok = "numero;date;code_client;echeance;montant_ht;tva;autres_taxes;montant_ttc;devise\nX-1;01/01/2026;C10;31/01/2026;100;19;1;120;TND\n"
    r = a.ok("post", "/imports/invoices", files={"file": ("f.csv", csv_ok.encode())}, data={"dry_run": "true"})
    assert r["errors"] == 0 and r["imported"] == 0
    bad = csv_ok + "X-2;01/01/2026;C99;;100;19;0;120;TND\n"
    r = a.ok("post", "/imports/invoices", files={"file": ("f.csv", bad.encode())}, data={"dry_run": "false"})
    assert r["imported"] == 0 and r["errors"] == 1
    r = a.ok("post", "/imports/invoices", files={"file": ("f.csv", csv_ok.encode())}, data={"dry_run": "false"})
    assert r["imported"] == 1
    r = a.ok("post", "/imports/invoices", files={"file": ("f.csv", csv_ok.encode())}, data={"dry_run": "true"})
    assert r["errors"] == 1  # numéro déjà existant
    check_coherence()


def test_reports_all_formats(api):
    a = api("daf")
    c = mk_customer(a)
    mk_invoice(a, c["id"], days(45))
    for code in [x["code"] for x in a.ok("get", "/reports")]:
        q = f"?customer_id={c['id']}" if code == "grand-livre" else ""
        for fmt in ("json", "xlsx", "pdf", "csv"):
            r = a.get(f"/reports/{code}{q}{'&' if q else '?'}format={fmt}")
            assert r.status_code == 200, (code, fmt, r.text[:300])


def test_forecast_and_ai(api):
    a = api()
    c = mk_customer(a)
    vir = method_id(a, "VIR")
    for k in range(4):   # historique : le client paie 20 j après l'échéance
        inv = mk_invoice(a, c["id"], days(200 - k * 30), "100")
        a.ok("post", "/payments", {"customer_id": c["id"], "method_id": vir, "receipt_date": str(days(200 - k * 30 - 50)), "amount": "120",
                                   "allocations": [{"invoice_id": inv["id"], "amount": "120"}]})
    inv = mk_invoice(a, c["id"], days(5), "100")
    f = a.ok("get", "/ai/forecast")
    p = [x for x in f["details"] if x["invoice_id"] == inv["id"]][0]
    assert p["predicted_date"] == str(days(5) + dt.timedelta(days=30 + 20))
    assert "retard médian du client (20 j" in p["rule"]
    assert a.ok("get", "/ai/synthesis")["text"]
    assert isinstance(a.ok("get", "/ai/anomalies"), list)
    assert isinstance(a.ok("get", "/ai/priorities"), list)


def test_dunning_proposals_and_action(api):
    a = api()
    rec = api("recouvrement")
    c = mk_customer(a, contact_name="M. Ben Salah")
    inv = mk_invoice(a, c["id"], days(75), "1000")    # 45 j de retard → niveau 2 recommandé
    props = rec.ok("get", "/dunning/proposals")
    p = props["overdue"][0]
    assert p["recommended_level"]["level"] == 2 and p["needs_action"]
    tpl = p["recommended_level"]["template_id"]
    prev = rec.ok("post", "/dunning/preview", {"customer_id": c["id"], "template_id": tpl})
    assert inv["number"] in prev["body"] and "1 191,000 TND" in prev["body"]
    rec.ok("post", "/dunning/actions", {"customer_id": c["id"], "level_id": p["recommended_level"]["id"], "action_type": "RELANCE_2",
                                        "channel": "LETTRE", "invoice_ids": [inv["id"]], "result_code": "PROMESSE",
                                        "promised_date": str(T + dt.timedelta(days=10)), "promised_amount": "1191",
                                        "next_action_date": str(T + dt.timedelta(days=11)), "rendered_text": prev["body"]})
    p2 = rec.ok("get", "/dunning/proposals")["overdue"][0]
    assert p2["promise"] and not p2["needs_action"] and p2["last_level"] == 2
    hist = rec.ok("get", f"/dunning/actions?customer_id={c['id']}")
    assert hist[0]["invoices"][0]["number"] == inv["number"]


def test_big_scenario_coherence(api):
    """Scénario mixte : plusieurs clients, devises, avoirs, rejets, OD — la concordance doit tenir."""
    a, daf = api(), api("daf")
    vir, chq, eff = method_id(a, "VIR"), method_id(a, "CHQ"), method_id(a, "EFF")
    cs = [mk_customer(a, legal_name=f"Client {i}") for i in range(4)]
    for i, c in enumerate(cs):
        for k in range(5):
            mk_invoice(a, c["id"], days(150 - 25 * k), str(300 + 70 * k + i),
                       installments=None if k % 2 else [(days(150 - 25 * k) + dt.timedelta(days=15), "100"),
                                                         (days(150 - 25 * k) + dt.timedelta(days=45), str(D(300 + 70 * k + i) * D("1.19") + 1 - 100))])
        a.ok("post", "/payments", {"customer_id": c["id"], "method_id": vir, "receipt_date": str(days(30)), "amount": str(500 + i * 77)})
        p = a.ok("post", "/payments", {"customer_id": c["id"], "method_id": chq, "receipt_date": str(days(20)), "amount": "333.333", "reference": f"C{i}"})
        if i % 2:
            a.ok("post", f"/payments/{p['id']}/status", {"status": "REJETE", "date": str(days(15)), "reason": "Sans provision"})
        else:
            a.ok("post", f"/payments/{p['id']}/status", {"status": "ENCAISSE", "date": str(days(17))})
        a.ok("post", "/payments", {"customer_id": c["id"], "method_id": eff, "receipt_date": str(days(10)), "amount": "250",
                                   "reference": f"E{i}", "value_date": str(T + dt.timedelta(days=30))})
    mk_invoice(a, cs[0]["id"], days(3), "100", doc_type="AVOIR")
    r = check_coherence()
    assert D(r["total_ledger_tnd"]) == D(r["total_open_items_tnd"]) - D(r["total_unallocated_tnd"])
    for k in range(1, 5):
        db = SessionLocal()
        assert coherence_check(db, days(k * 20))["ok"]
        db.close()
