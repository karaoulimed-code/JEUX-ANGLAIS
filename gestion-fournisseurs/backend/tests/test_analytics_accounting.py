"""Balance âgée, DPO, délai de paiement, prévisions, devises, écritures, rapprochement auxiliaire/général,
clôture de période, achats et engagements."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models import JournalEntry, Setting
from app.security import BusinessError
from app.services import accounting as A, analytics as AN, invoices as I, payments as P, purchasing as PU
from tests.conftest import TODAY, L


def test_aged_balance_buckets_and_as_of(w):
    s = w.supplier(rs_code=None, days=30)
    a = w.validate(w.invoice(s, [L(q="1", pu="100.000")], number="A", days_ago=10))     # non échue
    b = w.validate(w.invoice(s, [L(q="1", pu="200.000")], number="B", days_ago=75))     # 45 j de retard
    c = w.validate(w.invoice(s, [L(q="1", pu="300.000")], number="C", days_ago=250))    # 220 j de retard
    res = AN.aged_balance(w.ctx("daf"), TODAY)
    t = res["totaux"]
    assert t["non_echu"] == a.total_ttc
    assert t["31_60"] == b.total_ttc
    assert t["plus_180"] == c.total_ttc
    assert t["total_brut"] == a.total_ttc + b.total_ttc + c.total_ttc
    # à une date antérieure, la facture A n'existe pas encore et C n'est en retard que de 120 j
    past = AN.aged_balance(w.ctx("daf"), TODAY - timedelta(days=100))
    assert past["totaux"]["total_brut"] == c.total_ttc
    assert past["totaux"]["91_180"] == c.total_ttc
    # un règlement postérieur à la date d'arrêté ne réduit pas la balance à cette date
    w.pay(s, [(c, c.total_ttc)], days_ago=0)
    assert AN.aged_balance(w.ctx("daf"), TODAY - timedelta(days=1))["totaux"]["plus_180"] == c.total_ttc
    assert AN.aged_balance(w.ctx("daf"), TODAY)["totaux"]["plus_180"] == 0


def test_aged_balance_credit_notes_and_advances(w):
    s = w.supplier(rs_code=None)
    w.validate(w.invoice(s, [L(q="1", pu="1000.000")], number="F"))
    w.validate(w.invoice(s, [L(q="1", pu="100.000")], number="AV", doc_type="avoir"))
    t = AN.aged_balance(w.ctx("daf"), TODAY)["totaux"]
    assert t["avoirs_non_imputes"] == Decimal("-119.000")
    assert t["total_net"] == t["total_brut"] - Decimal("119.000")


def test_dpo_and_payment_delay(w):
    s = w.supplier(rs_code=None)
    a = w.validate(w.invoice(s, [L(q="1", pu="1000.000")], number="A", days_ago=100))  # 1 191
    b = w.validate(w.invoice(s, [L(q="1", pu="1000.000")], number="B", days_ago=40))   # 1 191
    w.pay(s, [(a, a.total_ttc)], days_ago=50)   # payée 50 j après facture, avant échéance? échéance J+30 -> en retard
    k = AN.kpis(w.ctx("daf"), TODAY, 365)
    assert k["total_dettes"] == b.total_ttc
    assert k["achats_ttc_periode"] == a.total_ttc + b.total_ttc
    # DPO = dettes / achats × 365 = 1191 / 2382 × 365 = 182.5
    assert k["dpo_jours"] == Decimal("182.500")
    assert k["delai_moyen_paiement_jours"] == Decimal("50.000")
    assert k["taux_paiement_a_echeance_pct"] == Decimal("0.000")
    assert k["dettes_echues"] == b.total_ttc  # échéance J-10


def test_forecast_categories(w):
    from app.models import Dispute
    s = w.supplier(rs_code=None, days=30)
    inv = w.validate(w.invoice(s, [L(q="1", pu="1000.000")], number="A", days_ago=10))  # échéance J+20
    w.db.add(Dispute(company_id=w.company.id, number="L1", supplier_id=s.id, invoice_id=inv.id, kind="prix",
                     contested_amount=Decimal("191.000"), reason="x", opened_at=TODAY))
    po = w.order(s, [L(q="10", pu="10.000")], days_ago=2)  # non livrée : probable
    fc = AN.forecast(w.ctx("daf"), TODAY)
    h30 = next(h for h in fc["horizons"] if h["jours"] == 30)
    assert h30["certain"] == Decimal("1000.000")
    assert h30["conditionnel"] == Decimal("191.000")
    h90 = next(h for h in fc["horizons"] if h["jours"] == 90)
    assert h90["probable"] == po.total_ttc
    h7 = next(h for h in fc["horizons"] if h["jours"] == 7)
    assert h7["certain"] == 0


def test_payment_plan_priorities(w):
    s1 = w.supplier("ESC", rs_code=None, early_discount_pct=Decimal("2"), early_discount_days=10, days=60)
    s2 = w.supplier("RET", rs_code=None, category="critique", days=30)
    a = w.validate(w.invoice(s1, [L(q="1", pu="1000.000")], number="1", days_ago=2))
    b = w.validate(w.invoice(s2, [L(q="1", pu="1000.000")], number="2", days_ago=45))
    plan = AN.payment_plan(w.ctx("daf"), TODAY, 30, Decimal("1500"))
    rec = {p["invoice_id"]: p for p in plan["propositions"]}
    assert rec[b.id]["recommandation"] == "payer_immediatement" and rec[b.id]["retenu"]
    assert rec[a.id]["recommandation"] == "report_a_negocier"  # trésorerie insuffisante après priorité
    assert any("accord écrit" in j for j in rec[a.id]["justification"])
    plan2 = AN.payment_plan(w.ctx("daf"), TODAY, 30, Decimal("5000"))
    rec2 = {p["invoice_id"]: p for p in plan2["propositions"]}
    assert rec2[a.id]["recommandation"] == "payer_anticipe_escompte"


def test_foreign_currency_fx_difference(w):
    from app.models import ExchangeRate
    w.db.add(ExchangeRate(company_id=w.company.id, currency="EUR", rate_date=TODAY - timedelta(days=5), rate=Decimal("3.400000")))
    w.db.flush()
    s = w.supplier("EU", rs_code=None, currency="EUR")
    inv = w.validate(w.invoice(s, [L(q="1", pu="1000.000", tva="0")], number="E1", days_ago=30))
    assert inv.exchange_rate == Decimal("3.300000") and inv.stamp_duty == 0
    assert inv.total_ttc_tnd == Decimal("3300.000")
    p = w.pay(s, [(inv, Decimal("1000.000"))])
    assert p.exchange_rate == Decimal("3.400000")
    assert p.allocations[0].fx_difference_tnd == Decimal("100.000")  # perte de change
    je = w.db.query(JournalEntry).filter_by(source_type="reglement", source_id=p.id).one()
    d = {l.account_code: (l.debit, l.credit) for l in je.lines}
    assert d["401"] == (Decimal("3300.000"), 0)
    assert d["655"] == (Decimal("100.000"), 0)
    assert d["5321"] == (0, Decimal("3400.000"))
    rec = AN.reconcile_aux_gl(w.ctx("resp_compta"), TODAY)
    assert rec["concordant"], rec


def test_entries_always_balanced_and_aux_gl_concordant(w):
    s = w.supplier()
    po = w.order(s, [L(q="10", pu="200.000"), L(desc="Immo", q="1", pu="5000.000", account_code="2281")])
    w.receive(po, [10, 1])
    inv = w.validate(w.invoice(s, [L(q="10", pu="200.000", order_line_id=po.lines[0].id),
                                   L(desc="Immo", q="1", pu="5000.000", order_line_id=po.lines[1].id, account_code="2281")],
                                  order=po))
    w.pay(s, [(inv, Decimal("3000.000"))], method="cheque")
    av = w.validate(w.invoice(s, [L(q="1", pu="100.000")], number="AV", doc_type="avoir"))
    I.allocate_credit(w.ctx("resp_compta"), av, inv, Decimal("119.000"), TODAY)
    for je in w.db.query(JournalEntry).all():
        assert sum(l.debit for l in je.lines) == sum(l.credit for l in je.lines), je.number
    first = w.db.query(JournalEntry).filter_by(source_type="facture", source_id=inv.id).one()
    accs = {l.account_code for l in first.lines}
    assert {"404", "43661", "43662", "2281"} <= accs  # fournisseur d'immobilisation et TVA sur immobilisations
    rec = AN.reconcile_aux_gl(w.ctx("resp_compta"), TODAY)
    assert rec["concordant"], rec
    tb = AN.trial_balance(w.ctx("resp_compta"), TODAY.replace(month=1, day=1), TODAY)
    assert tb["totaux"]["solde_final"] == rec["solde_auxiliaire"]


def test_validated_entries_and_period_lock(w):
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="100.000")], days_ago=40))
    ids = [je.id for je in w.db.query(JournalEntry).all()]
    assert A.validate_entries(w.ctx("resp_compta"), ids) == 1
    w.db.add(Setting(company_id=w.company.id, key="date_cloture", value=(TODAY - timedelta(days=30)).isoformat()))
    w.db.flush()
    with pytest.raises(BusinessError) as e:
        w.invoice(s, [L(q="1", pu="5.000")], number="OLD", days_ago=35)
        I.submit_invoice(w.ctx("agent_compta"), w.db.query(type(inv)).filter_by(supplier_number="OLD").one())
    assert e.value.code == "periode_close"


def test_purchase_request_and_order_controls(w):
    s = w.supplier()
    pr = PU.create_request(w.ctx("agent_compta"), {"request_date": TODAY, "lines": [
        {"description": "Ramettes", "quantity": Decimal("10"), "estimated_unit_price": Decimal("12")}]})
    PU.submit_request(w.ctx("agent_compta"), pr)
    with pytest.raises(BusinessError):
        PU.decide_request(w.ctx("agent_compta"), pr, True, None)
    PU.decide_request(w.ctx("daf"), pr, True, "ok")
    po = PU.create_order(w.ctx("resp_achats"), {"supplier_id": s.id, "request_id": pr.id, "order_date": TODAY,
                                                "lines": [L(q="10", pu="12.000")]})
    PU.submit_order(w.ctx("resp_achats"), po)
    with pytest.raises(BusinessError):
        PU.approve_order(w.ctx("resp_achats"), po, True)
    big = PU.create_order(w.ctx("resp_achats"), {"supplier_id": s.id, "order_date": TODAY, "lines": [L(q="1", pu="60000.000")]})
    PU.submit_order(w.ctx("resp_achats"), big)
    with pytest.raises(BusinessError):
        PU.approve_order(w.ctx("daf"), big, True)  # au-delà du seuil : DG
    PU.approve_order(w.ctx("dg"), big, True)
    PU.approve_order(w.ctx("daf"), po, True)
    with pytest.raises(BusinessError):  # approbateur ne réceptionne pas
        PU.create_receipt(w.ctx("daf"), {"order_id": po.id, "receipt_date": TODAY,
                                         "lines": [{"order_line_id": po.lines[0].id, "qty_received": Decimal("1")}]})
    with pytest.raises(BusinessError):  # sur-réception
        PU.create_receipt(w.ctx("agent2"), {"order_id": po.id, "receipt_date": TODAY,
                                            "lines": [{"order_line_id": po.lines[0].id, "qty_received": Decimal("11")}]})
    PU.create_receipt(w.ctx("agent2"), {"order_id": po.id, "receipt_date": TODAY,
                                        "lines": [{"order_line_id": po.lines[0].id, "qty_received": Decimal("4")}]})
    assert po.status == "partiellement_recue"
    com = {c["numero"]: c for c in PU.commitments(w.ctx("daf"))}
    assert com[po.number]["restant_ttc"] == po.total_ttc
    assert com[po.number]["recu_non_facture_ht"] == Decimal("48.000")
    with pytest.raises(BusinessError):
        PU.cancel_order(w.ctx("daf"), po, "plus besoin")
    PU.close_order(w.ctx("resp_achats"), po, "reliquat abandonné")
    assert po.number not in {c["numero"] for c in PU.commitments(w.ctx("daf"))}


def test_supplier_duplicates(w):
    from app.services import suppliers as S
    s = w.supplier("D1")
    with pytest.raises(BusinessError) as e:
        S.create_supplier(w.ctx("resp_achats"), {"code": "D2", "legal_name": "Autre", "tax_id": s.tax_id})
    assert e.value.status == 409
    _, warns = S.create_supplier(w.ctx("resp_achats"), {"code": "D3", "legal_name": "Fournisseur D1 SARL"})
    assert any("raison sociale proche" in x for x in warns)


def test_supplier_risk_dependency(w):
    big = w.supplier("BIG", rs_code=None, category="critique")
    small = w.supplier("SMALL", rs_code=None)
    w.validate(w.invoice(big, [L(q="1", pu="9000.000")], number="1"))
    w.validate(w.invoice(small, [L(q="1", pu="100.000")], number="2"))
    r = {x["code"]: x for x in AN.supplier_risk(w.ctx("daf"), TODAY)}
    assert r["BIG"]["part_achats_pct"] > 90
    assert r["BIG"]["niveau"] in ("modere", "eleve", "critique")
    assert r["SMALL"]["niveau"] == "faible"
