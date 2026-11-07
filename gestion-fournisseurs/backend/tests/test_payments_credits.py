"""Règlements partiels et groupés, affectation, avances, avoirs, acomptes, rejets, autorisations."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models import JournalEntry
from app.security import BusinessError
from app.services import invoices as I, payments as P
from tests.conftest import TODAY, L


def test_partial_payment_with_withholding(w):
    s = w.supplier()
    inv = w.validate(w.invoice(s, [L(q="10", pu="100.000")], days_ago=5), force=True)
    # TTC = 1 191.000 ; RS 1,5 % = 17.865
    p = w.pay(s, [(inv, Decimal("595.500"))])
    assert p.rs_amount == Decimal("8.933")      # 17.865 × 595.5 / 1191 (arrondi)
    assert p.cash_amount == Decimal("586.567")
    assert I.balance(w.db, inv) == Decimal("595.500")
    p2 = w.pay(s, [(inv, Decimal("595.500"))])
    assert I.balance(w.db, inv) == 0
    assert p.rs_amount + p2.rs_amount == Decimal("17.865")  # le dernier règlement prend le reliquat exact


def test_overpayment_and_planned_payment_blocked(w):
    s = w.supplier()
    inv = w.validate(w.invoice(s, [L(q="1", pu="100.000")]))
    with pytest.raises(BusinessError):
        P.create_payment(w.ctx("tresorier"), {"supplier_id": s.id, "method": "cheque", "payment_date": TODAY,
                                              "allocations": [{"invoice_id": inv.id, "amount": Decimal("200")}]})
    P.create_payment(w.ctx("tresorier"), {"supplier_id": s.id, "method": "cheque", "payment_date": TODAY,
                                          "allocations": [{"invoice_id": inv.id, "amount": Decimal("100")}]})
    with pytest.raises(BusinessError):  # déjà en préparation : double paiement impossible
        P.create_payment(w.ctx("tresorier"), {"supplier_id": s.id, "method": "cheque", "payment_date": TODAY,
                                              "allocations": [{"invoice_id": inv.id, "amount": Decimal("50")}]})


def test_grouped_payment(w):
    s = w.supplier(rs_code=None)
    a = w.validate(w.invoice(s, [L(q="1", pu="100.000")], number="A"))
    b = w.validate(w.invoice(s, [L(q="2", pu="100.000")], number="B"))
    p = w.pay(s, [(a, a.total_ttc), (b, b.total_ttc)], method="cheque", reference="CHQ1")
    assert p.cash_amount == a.total_ttc + b.total_ttc
    assert I.balance(w.db, a) == I.balance(w.db, b) == 0


def test_payment_segregation_and_double_signature(w):
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="60000.000")], days_ago=1), force=True)
    p, _ = P.create_payment(w.ctx("tresorier"), {"supplier_id": s.id, "method": "virement", "payment_date": TODAY,
                                                 "treasury_account_id": w.bank.id,
                                                 "allocations": [{"invoice_id": inv.id, "amount": inv.total_ttc}]})
    P.submit_payment(w.ctx("tresorier"), p)
    assert p.required_approvals == 2
    P.approve_payment(w.ctx("daf"), p)
    assert p.status == "a_approuver"
    with pytest.raises(BusinessError):
        P.approve_payment(w.ctx("daf"), p)
    P.approve_payment(w.ctx("dg"), p)
    assert p.status == "approuve"
    with pytest.raises(BusinessError):  # l'autorisateur n'exécute pas
        P.execute_payment(w.ctx("daf"), p)
    P.execute_payment(w.ctx("tresorier"), p)
    assert p.status == "emis"


def test_preparer_cannot_approve(w):
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="10.000")]))
    p, _ = P.create_payment(w.ctx("daf"), {"supplier_id": s.id, "method": "cheque", "payment_date": TODAY,
                                           "allocations": [{"invoice_id": inv.id, "amount": inv.total_ttc}]})
    P.submit_payment(w.ctx("daf"), p)
    with pytest.raises(BusinessError):
        P.approve_payment(w.ctx("daf"), p)


def test_unverified_rib_blocks_transfer(w):
    from app.services import suppliers as S
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="10.000")]))
    S.add_bank_account(w.ctx("agent_compta"), s, {"bank_name": "Nouvelle banque", "rib": "08008000000000099999"})
    with pytest.raises(BusinessError) as e:
        P.create_payment(w.ctx("tresorier"), {"supplier_id": s.id, "method": "virement", "payment_date": TODAY,
                                              "allocations": [{"invoice_id": inv.id, "amount": inv.total_ttc}]})
    assert e.value.code == "rib_non_verifie"


def test_bank_change_requires_other_person(w):
    from app.services import suppliers as S
    s = w.supplier()
    acc, warn = S.add_bank_account(w.ctx("resp_compta"), s, {"bank_name": "X", "rib": "12345678901234567890"})
    assert any("Clé RIB" in x for x in warn)
    with pytest.raises(BusinessError):
        S.verify_bank_account(w.ctx("resp_compta"), acc, True, None)
    S.verify_bank_account(w.ctx("daf"), acc, True, "contre-appel")


def test_rejected_cheque_restores_debt_and_reverses_entries(w):
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="100.000")]))
    p = w.pay(s, [(inv, inv.total_ttc)], method="cheque", reference="CHQ9")
    assert I.balance(w.db, inv) == 0
    P.reject_payment(w.ctx("tresorier"), p, "Chèque rejeté — défaut de provision")
    assert I.balance(w.db, inv) == inv.total_ttc
    assert p.status == "rejete"
    reversals = w.db.query(JournalEntry).filter(JournalEntry.source_type == "reglement",
                                                JournalEntry.reversal_of_id.is_not(None)).count()
    assert reversals == 1


def test_disputed_amount_not_payable(w):
    from app.models import Dispute
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="1000.000")]))
    w.db.add(Dispute(company_id=w.company.id, number="LT1", supplier_id=s.id, invoice_id=inv.id, kind="prix",
                     contested_amount=Decimal("300.000"), reason="prix", opened_at=TODAY))
    w.db.flush()
    assert I.display_status(w.db, inv) == "en_litige"
    assert P.payable_amount(w.db, inv) == inv.total_ttc - Decimal("300.000")
    with pytest.raises(BusinessError):
        P.create_payment(w.ctx("tresorier"), {"supplier_id": s.id, "method": "cheque", "payment_date": TODAY,
                                              "allocations": [{"invoice_id": inv.id, "amount": inv.total_ttc}]})


def test_advance_then_allocation(w):
    s = w.supplier(rs_code=None)
    p, _ = P.create_payment(w.ctx("tresorier"), {"supplier_id": s.id, "kind": "avance", "method": "virement",
                                                 "treasury_account_id": w.bank.id, "payment_date": TODAY - timedelta(days=20),
                                                 "unallocated_amount": Decimal("500.000")})
    P.submit_payment(w.ctx("tresorier"), p)
    P.approve_payment(w.ctx("daf"), p)
    P.execute_payment(w.ctx("tresorier"), p)
    je = w.db.query(JournalEntry).filter_by(source_type="reglement", source_id=p.id).one()
    assert {l.account_code for l in je.lines if l.debit} == {"409"}
    inv = w.validate(w.invoice(s, [L(q="1", pu="1000.000")]))
    P.allocate_later(w.ctx("tresorier"), p, inv, Decimal("500.000"), TODAY)
    assert I.balance(w.db, inv) == inv.total_ttc - Decimal("500.000")
    assert P.unallocated(w.db, p) == 0
    od = w.db.query(JournalEntry).filter_by(source_type="imputation_avance").one()
    assert {(l.account_code, l.debit > 0) for l in od.lines} == {("401", True), ("409", False)}


def test_credit_note_allocation(w):
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="1000.000")], number="F10"))
    av = w.validate(w.invoice(s, [L(q="1", pu="100.000")], number="AV10", doc_type="avoir", origin_invoice_id=inv.id))
    assert av.stamp_duty == 0 and av.rs_amount == 0
    assert I.balance(w.db, av) == -Decimal("119.000")
    I.allocate_credit(w.ctx("resp_compta"), av, inv, Decimal("119.000"), TODAY)
    assert I.balance(w.db, inv) == inv.total_ttc - Decimal("119.000")
    assert I.balance(w.db, av) == 0
    with pytest.raises(BusinessError):
        I.allocate_credit(w.ctx("resp_compta"), av, inv, Decimal("1"), TODAY)


def test_down_payment_invoice_imputation(w):
    s = w.supplier(rs_code=None)
    ac = w.validate(w.invoice(s, [L(q="1", pu="300.000")], number="ACP1", doc_type="acompte", days_ago=30))
    assert ac.lines[0].account_code == "409"
    with pytest.raises(BusinessError):  # acompte non encore payé
        fin0 = w.validate(w.invoice(s, [L(q="1", pu="1000.000")], number="FIN0"))
        I.allocate_credit(w.ctx("resp_compta"), ac, fin0, Decimal("357.000"), TODAY)
    w.pay(s, [(ac, ac.total_ttc)], days_ago=25)
    fin = w.validate(w.invoice(s, [L(q="1", pu="1000.000")], number="FIN1"))
    assert I.available_credit(w.db, ac) == Decimal("357.000")
    I.allocate_credit(w.ctx("resp_compta"), ac, fin, Decimal("357.000"), TODAY)
    assert I.balance(w.db, fin) == fin.total_ttc - Decimal("357.000")
    je = w.db.query(JournalEntry).filter_by(source_type="imputation_acompte").one()
    d = {l.account_code: (l.debit, l.credit) for l in je.lines}
    assert d["401"] == (Decimal("357.000"), 0)
    assert d["409"] == (0, Decimal("300.000"))
    assert d["43662"] == (0, Decimal("57.000"))


def test_payment_run_groups_by_supplier(w):
    s1, s2 = w.supplier("A1", rs_code=None), w.supplier("A2", rs_code=None)
    a = w.validate(w.invoice(s1, [L(q="1", pu="10.000")], number="1"))
    b = w.validate(w.invoice(s1, [L(q="1", pu="20.000")], number="2"))
    c = w.validate(w.invoice(s2, [L(q="1", pu="30.000")], number="3"))
    run, pays, _ = P.create_run(w.ctx("tresorier"), {"planned_date": TODAY, "treasury_account_id": w.bank.id,
                                                    "method": "cheque", "items": [{"invoice_id": x.id} for x in (a, b, c)]})
    assert len(pays) == 2 and all(p.status == "a_approuver" for p in pays)


def test_bank_reconciliation(w):
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="100.000")]))
    p = w.pay(s, [(inv, inv.total_ttc)], method="cheque", reference="CHQ77")
    st = P.reconciliation_state(w.ctx("tresorier"), w.bank.id)
    assert st["paiements_emis_non_debites"] == inv.total_ttc
    res = P.import_statement(w.ctx("tresorier"), w.bank.id, [
        {"operation_date": TODAY, "label": "CHQ 77", "reference": "CHQ77", "amount": -inv.total_ttc}])
    assert res["rapprochees_auto"] == 1 and p.status == "debite"
    st = P.reconciliation_state(w.ctx("tresorier"), w.bank.id)
    assert st["solde_releve"] == Decimal("100000.000") - inv.total_ttc
    assert st["paiements_emis_non_debites"] == 0


def test_bill_of_exchange_flow(w):
    s = w.supplier(rs_code=None)
    inv = w.validate(w.invoice(s, [L(q="1", pu="100.000")]))
    p = w.pay(s, [(inv, inv.total_ttc)], method="effet", reference="LC-1", due_date=TODAY + timedelta(days=60))
    je = w.db.query(JournalEntry).filter_by(source_type="reglement", source_id=p.id).one()
    assert any(l.account_code == "403" and l.credit for l in je.lines)
    P.clear_payment(w.ctx("tresorier"), p, TODAY)
    je2 = w.db.query(JournalEntry).filter_by(source_type="effet", source_id=p.id).one()
    assert any(l.account_code == "403" and l.debit for l in je2.lines)
