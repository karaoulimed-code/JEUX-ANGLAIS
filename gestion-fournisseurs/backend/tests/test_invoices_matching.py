"""Enregistrement des factures, TVA, retenue à la source, rapprochement à trois niveaux, anomalies."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.security import BusinessError
from app.services import invoices as I
from tests.conftest import TODAY, L


def codes(inv):
    return {a["code"] for a in inv.anomalies or []}


def test_invoice_totals_stamp_rs_due_date(w):
    s = w.supplier(days=60)
    inv = w.invoice(s, [L(q="10", pu="100.000", tva="19"), L(desc="B", q="3", pu="33.333", tva="7")])
    # HT = 1000 + 99.999 ; TVA = 190 + 7.000 ; timbre 1.000
    assert inv.total_ht == Decimal("1099.999")
    assert inv.total_tva == Decimal("197.000")
    assert inv.stamp_duty == Decimal("1.000")
    assert inv.total_ttc == Decimal("1297.999")
    # RS 1,5 % sur TTC (≥ 1 000 DT)
    assert inv.rs_amount == Decimal("19.470")
    assert inv.net_to_pay == Decimal("1278.529")
    assert inv.due_date == inv.invoice_date + timedelta(days=60)
    assert inv.workflow_status == "brouillon"


def test_rs_below_threshold_and_end_of_month(w):
    s = w.supplier(payment_terms_type="fin_de_mois", days=30)
    inv = w.invoice(s, [L(q="1", pu="500.000")])
    assert inv.rs_amount == 0  # 595 + 1 < 1 000 DT
    assert inv.due_date.day in (28, 29, 30, 31)
    assert (inv.due_date + timedelta(days=1)).day == 1


def test_rs_honoraires_no_threshold(w):
    s = w.supplier("H1", rs_code="RS_HONO_3")
    inv = w.invoice(s, [L(q="1", pu="200.000")])
    assert inv.rs_amount == Decimal("7.170")  # 3 % de 239.000


def test_tva_controls(w):
    s = w.supplier()
    inv = w.invoice(s, [L(tva="18")])
    assert "TVA_INCOHERENTE" in codes(inv)
    inv2 = w.invoice(s, [L(amount_tva="150.000")], number="F-2")
    assert "TVA_INCOHERENTE" in codes(inv2)
    ns = w.supplier("NS", vat_regime="non_assujetti", rs_code=None)
    inv3 = w.invoice(ns, [L()], number="F-3")
    assert "TVA_INCOHERENTE" in codes(inv3)


def test_calculation_error_and_declared_total(w):
    s = w.supplier()
    inv = w.invoice(s, [L(amount_ht="1500.000")], declared_total_ttc=Decimal("9999"))
    assert "ERREUR_CALCUL" in codes(inv)


def test_duplicate_detection(w):
    s = w.supplier()
    a = w.invoice(s, [L()], number="FA-00123")
    w.validate(a, force=True)
    b = w.invoice(s, [L()], number="fa 123")
    assert "DOUBLON" in codes(b)
    c = w.invoice(s, [L()], number="FA-999", days_ago=12)
    assert "DOUBLON_SUSPECT" in codes(c)
    with pytest.raises(BusinessError) as e:
        I.submit_invoice(w.ctx("agent_compta"), b)
        I.approve_invoice(w.ctx("resp_compta"), b)
    assert e.value.code == "anomalies_bloquantes"


def test_three_way_match_ok(w):
    s = w.supplier()
    po = w.order(s, [L(q="10", pu="100.000")])
    w.receive(po, [10])
    inv = w.invoice(s, [L(q="10", pu="100.000", order_line_id=po.lines[0].id)], order=po)
    w.validate(inv)
    assert inv.workflow_status == "validee"
    assert inv.matching_status == "conforme"
    assert po.lines[0].qty_invoiced == 10


def test_three_way_quantity_not_received(w):
    s = w.supplier()
    po = w.order(s, [L(q="10")])
    w.receive(po, [6])
    inv = w.invoice(s, [L(q="8", order_line_id=po.lines[0].id)], order=po)
    assert "QTE_NON_RECEPTIONNEE" in codes(inv)
    I.submit_invoice(w.ctx("agent_compta"), inv)
    with pytest.raises(BusinessError):
        I.approve_invoice(w.ctx("resp_compta"), inv)


def test_three_way_cumulative_over_invoicing(w):
    s = w.supplier()
    po = w.order(s, [L(q="10")])
    w.receive(po, [10])
    a = w.invoice(s, [L(q="6", order_line_id=po.lines[0].id)], order=po, number="P1")
    w.validate(a)
    b = w.invoice(s, [L(q="6", order_line_id=po.lines[0].id)], order=po, number="P2")
    assert "QTE_NON_RECEPTIONNEE" in codes(b) and "QTE_SUP_COMMANDE" in codes(b)


def test_price_tolerance(w):
    s = w.supplier()
    po = w.order(s, [L(q="10", pu="100.000")])
    w.receive(po, [10])
    within = w.invoice(s, [L(q="5", pu="101.500", order_line_id=po.lines[0].id)], order=po, number="T1")
    assert [a["gravite"] for a in within.anomalies if a["code"] == "ECART_PRIX"] == ["avertissement"]
    over = w.invoice(s, [L(q="5", pu="105.000", order_line_id=po.lines[0].id)], order=po, number="T2")
    assert [a["gravite"] for a in over.anomalies if a["code"] == "ECART_PRIX"] == ["bloquante"]


def test_invoice_without_po_threshold(w):
    s = w.supplier()
    small = w.invoice(s, [L(q="1", pu="100.000")], number="S1")
    big = w.invoice(s, [L(q="10", pu="100.000")], number="S2")
    g = {a["code"]: a["gravite"] for a in small.anomalies}
    assert g["SANS_BC"] == "avertissement"
    assert {a["code"]: a["gravite"] for a in big.anomalies}["SANS_BC"] == "bloquante"


def test_missing_attachment_blocks(w):
    s = w.supplier()
    inv = w.invoice(s, [L(q="1", pu="10.000")], attach=False)
    assert "SANS_JUSTIFICATIF" in codes(inv)


def test_unauthorized_supplier(w):
    from app.services import suppliers as S
    s = w.supplier()
    S.approve_supplier(w.ctx("daf"), s, "bloque")
    inv = w.invoice(s, [L(q="1", pu="10.000")])
    assert "FOURNISSEUR_NON_AUTORISE" in codes(inv)


def test_force_requires_daf_and_justification(w):
    s = w.supplier()
    inv = w.invoice(s, [L(q="10", pu="100.000")])  # sans BC, > seuil -> bloquante
    I.submit_invoice(w.ctx("agent_compta"), inv)
    with pytest.raises(BusinessError):
        I.approve_invoice(w.ctx("resp_compta"), inv, force=True, justification="justification suffisante ok")
    with pytest.raises(BusinessError):
        I.approve_invoice(w.ctx("daf"), inv, force=True, justification="court")
    I.approve_invoice(w.ctx("daf"), inv, force=True, justification="Achat urgent validé par la direction")
    assert inv.workflow_status == "validee" and inv.forced


def test_approval_levels_and_segregation(w):
    s = w.supplier()
    po = w.order(s, [L(q="100", pu="150.000")])  # 17 851 TTC -> 2 niveaux
    w.receive(po, [100])
    inv = w.invoice(s, [L(q="100", pu="150.000", order_line_id=po.lines[0].id)], order=po)
    I.submit_invoice(w.ctx("agent_compta"), inv)
    assert inv.required_levels == 2
    with pytest.raises(BusinessError):  # le saisisseur ne valide pas
        I.approve_invoice(w.ctx("agent_compta"), inv)
    I.approve_invoice(w.ctx("resp_compta"), inv)
    assert inv.workflow_status == "en_attente_validation"
    with pytest.raises(BusinessError):  # niveau 2 réservé DAF/DG
        I.approve_invoice(w.ctx("resp_compta"), inv)
    I.approve_invoice(w.ctx("daf"), inv)
    assert inv.workflow_status == "validee"


def test_validated_invoice_immutable_and_cancel(w):
    s = w.supplier()
    inv = w.validate(w.invoice(s, [L(q="1", pu="100.000")]))
    with pytest.raises(BusinessError):
        I.update_invoice(w.ctx("agent_compta"), inv, {"supplier_number": "X"})
    with pytest.raises(BusinessError):
        I.cancel_invoice(w.ctx("agent_compta"), inv, "erreur de saisie")
    I.cancel_invoice(w.ctx("resp_compta"), inv, "erreur de saisie")
    assert inv.workflow_status == "annulee"
    assert I.balance(w.db, inv) == 0


def test_display_statuses(w):
    s = w.supplier()
    inv = w.invoice(s, [L(q="1", pu="100.000")], days_ago=60)
    assert I.display_status(w.db, inv) == "brouillon"
    w.validate(inv)
    assert I.display_status(w.db, inv) == "echue"
    w.pay(s, [(inv, Decimal("50.000"))])
    assert I.display_status(w.db, inv) == "partiellement_reglee"
    w.pay(s, [(inv, I.balance(w.db, inv))])
    assert I.display_status(w.db, inv) == "reglee"
    inv2 = w.validate(w.invoice(s, [L(q="1", pu="100.000")], number="NE", days_ago=1))
    assert I.display_status(w.db, inv2) == "non_echue"


def test_price_anomaly_vs_history(w):
    s = w.supplier()
    for n in range(3):
        w.validate(w.invoice(s, [L(q="1", pu="100.000", item_ref="ART1")], number=f"H{n}", days_ago=100 - n * 20), force=True)
    inv = w.invoice(s, [L(q="1", pu="130.000", item_ref="ART1")], number="H9")
    assert "PRIX_ANORMAL" in codes(inv)


def test_receiver_cannot_control_invoice(w):
    from app.services import purchasing as PU
    s = w.supplier()
    po = w.order(s, [L(q="1", pu="100.000")])
    PU.create_receipt(w.ctx("resp_compta"), {"order_id": po.id, "receipt_date": TODAY,
                                             "lines": [{"order_line_id": po.lines[0].id, "qty_received": 1}]})
    inv = w.invoice(s, [L(q="1", pu="100.000", order_line_id=po.lines[0].id)], order=po)
    I.submit_invoice(w.ctx("agent_compta"), inv)
    with pytest.raises(BusinessError) as e:
        I.approve_invoice(w.ctx("resp_compta"), inv)
    assert e.value.code == "separation_taches"
    I.approve_invoice(w.ctx("daf"), inv)
    assert inv.workflow_status == "validee"
