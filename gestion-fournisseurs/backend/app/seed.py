"""Données de référence (paramètres fiscaux tunisiens) et données de DÉMONSTRATION.

IMPORTANT — Les taux ci-dessous ont été relevés le 07/11/2026 à partir de sources secondaires
(sites spécialisés commentant la loi de finances 2026) qui divergent sur certains points.
Ils sont tous marqués « à vérifier » (to_verify=True) : l'expert-comptable de l'entreprise doit les
confirmer (Code de l'IRPP et de l'IS art. 52, Code de la TVA, Code des droits d'enregistrement et de timbre)
avant mise en production. Ils sont modifiables dans Paramètres > Taux, sans toucher au code.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Company, TaxRate, TreasuryAccount, User
from .security import hash_password

CHECKED = date(2026, 11, 7)

TAX_RATES = [
    # kind, code, label, rate, fixed, threshold, valid_from, reference
    ("TVA", "TVA19", "TVA taux normal 19 %", "19", "0", "0", date(2018, 1, 1), "Code de la TVA, art. 7 (LF 2018)"),
    ("TVA", "TVA13", "TVA taux intermédiaire 13 %", "13", "0", "0", date(2018, 1, 1), "Code de la TVA, art. 7"),
    ("TVA", "TVA7", "TVA taux réduit 7 %", "7", "0", "0", date(2018, 1, 1), "Code de la TVA, art. 7"),
    ("TVA", "TVA0", "Exonéré / hors champ (0 %)", "0", "0", "0", date(2000, 1, 1), "Code de la TVA, art. 9 et tableaux A/B"),
    ("TIMBRE", "TIMBRE_FACTURE", "Droit de timbre sur facture (montant fixe)", "0", "1.000", "0", date(2022, 1, 1),
     "Code des droits d'enregistrement et de timbre — montant 1,000 DT selon sources consultées, à confirmer"),
    ("RS", "RS_ACHATS_1_5", "RS 1,5 % — acquisitions de biens/services ≥ 1 000 DT TTC", "1.5", "0", "1000.000",
     date(2021, 1, 1), "Code IRPP/IS art. 52 — seuil 1 000 DT TTC ; non modifié par LF 2026 selon sources consultées"),
    ("RS", "RS_ACHATS_REDUIT", "RS taux réduit sur acquisitions (fournisseurs à taux d'IS réduit) — à confirmer",
     "1", "0", "1000.000", date(2021, 1, 1), "Code IRPP/IS art. 52 — sources divergentes, à confirmer"),
    ("RS", "RS_HONO_3", "RS 3 % — honoraires personnes morales et BNC au régime réel", "3", "0", "0",
     date(2021, 1, 1), "Code IRPP/IS art. 52"),
    ("RS", "RS_HONO_10", "RS 10 % — honoraires BNC au régime forfaitaire", "10", "0", "0", date(2021, 1, 1),
     "Code IRPP/IS art. 52"),
    ("RS", "RS_LOYERS_10", "RS 10 % — loyers", "10", "0", "0", date(2021, 1, 1), "Code IRPP/IS art. 52"),
    ("RS", "RS_NON_RESIDENT_15", "RS 15 % — rémunérations versées à des non-résidents (hors convention)", "15", "0", "0",
     date(2021, 1, 1), "Code IRPP/IS art. 52 — vérifier la convention fiscale applicable"),
]


def init_reference(db: Session, company_id: int) -> None:
    if db.scalar(select(TaxRate).where(TaxRate.company_id == company_id).limit(1)):
        return
    for kind, code, label, rate, fixed, thr, vf, ref in TAX_RATES:
        db.add(TaxRate(company_id=company_id, kind=kind, code=code, label=label, rate=Decimal(rate),
                       fixed_amount=Decimal(fixed), threshold=Decimal(thr), valid_from=vf, legal_reference=ref,
                       verified_on=CHECKED, to_verify=True))
    db.flush()


def create_company(db: Session, name: str, tax_id: str | None, admin_email: str, admin_password: str,
                   admin_name: str = "Administrateur", is_demo: bool = False) -> tuple[Company, User]:
    c = Company(name=name, tax_id=tax_id, is_demo=is_demo)
    db.add(c)
    db.flush()
    u = User(company_id=c.id, email=admin_email.lower(), full_name=admin_name, role="admin",
             password_hash=hash_password(admin_password))
    db.add(u)
    db.flush()
    init_reference(db, c.id)
    return c, u


def rib_with_key(first18: str) -> str:
    key = 97 - (int(first18) * 100) % 97
    return f"{first18}{key:02d}"


DEMO_PASSWORD = "Demo2026pass"
DEMO_USERS = [
    ("admin@demo.tn", "Amel Admin", "admin"), ("dg@demo.tn", "Karim Directeur", "dg"),
    ("daf@demo.tn", "Sonia DAF", "daf"), ("achats@demo.tn", "Walid Achats", "resp_achats"),
    ("compta@demo.tn", "Leila Comptable", "resp_compta"), ("agent@demo.tn", "Hichem Agent", "agent_compta"),
    ("tresor@demo.tn", "Nadia Trésorière", "tresorier"), ("lecture@demo.tn", "Auditeur Lecture", "lecture"),
]


def load_demo(db: Session) -> Company:
    """Crée une entreprise fictive complète en passant par les services métier (données cohérentes)."""
    from .models import ExchangeRate
    from .security import Ctx
    from .services import invoices as inv_svc, payments as pay_svc, purchasing as po_svc, suppliers as sup_svc
    from .models import Attachment, Dispute, SupplierContract, SupplierEvaluation
    from .services.common import next_number

    existing = db.scalar(select(Company).where(Company.is_demo.is_(True)))
    if existing:
        return existing
    c, admin = create_company(db, "SOCIÉTÉ DÉMO SARL — données fictives", "0000000/A/M/000",
                              DEMO_USERS[0][0], DEMO_PASSWORD, DEMO_USERS[0][1], is_demo=True)
    users = {"admin": admin}
    for email, name, role in DEMO_USERS[1:]:
        u = User(company_id=c.id, email=email, full_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
        db.add(u)
        db.flush()
        users[role] = u

    def ctx(role):
        return Ctx(db=db, user=users[role], ip="demo")

    t = date.today()
    for back, rate in ((400, "3.3500"), (120, "3.3900"), (60, "3.4100"), (20, "3.4300"), (0, "3.4500")):
        db.add(ExchangeRate(company_id=c.id, currency="EUR", rate_date=t - timedelta(days=back), rate=Decimal(rate),
                            source="Fictif (démo)"))
    bank = TreasuryAccount(company_id=c.id, name="Banque principale (démo)", bank_name="Banque Démo",
                           rib=rib_with_key("010010000000000001"), account_code="5321",
                           opening_balance=Decimal("250000.000"), opening_date=t - timedelta(days=400))
    db.add(bank)
    db.flush()

    sup_specs = [
        ("F001", "Alpha Matériaux SARL", "1111111/A/M/000", "strategique", "RS_ACHATS_1_5", 60, "fin_de_mois", "2", "15", "0"),
        ("F002", "Bêta Emballages SA", "2222222/B/M/000", "regulier", "RS_ACHATS_1_5", 30, "net", "0", "0", "8"),
        ("F003", "Gamma Services Informatiques", "3333333/C/P/000", "critique", "RS_HONO_3", 30, "net", "0", "0", "0"),
        ("F004", "Delta Transport", "4444444/D/N/000", "occasionnel", "RS_ACHATS_1_5", 0, "net", "0", "0", "0"),
        ("F005", "Europa Machines GmbH", None, "strategique", None, 90, "net", "0", "0", "0"),
        ("F006", "Cabinet Epsilon Conseil", "6666666/E/P/000", "regulier", "RS_HONO_3", 15, "net", "0", "0", "0"),
    ]
    sups = {}
    for i, (code, name, mf, cat, rs, days, kind, disc, disc_days, pen) in enumerate(sup_specs, 1):
        s, _ = sup_svc.create_supplier(ctx("resp_achats"), {
            "code": code, "legal_name": name, "tax_id": mf, "category": cat, "rs_code": rs,
            "payment_terms_days": days, "payment_terms_type": kind, "early_discount_pct": Decimal(disc),
            "early_discount_days": int(disc_days), "late_penalty_pct": Decimal(pen), "city": "Tunis" if mf else "Munich",
            "country": "TN" if mf else "DE", "is_resident": bool(mf), "currency": "TND" if mf else "EUR",
            "sector": ["Matériaux", "Emballage", "Informatique", "Transport", "Équipements", "Conseil"][i - 1],
            "email": f"contact@{code.lower()}.demo", "phone": "+216 71 000 00" + str(i)}, force=True)
        sup_svc.approve_supplier(ctx("resp_compta"), s, "actif")
        acc, _ = sup_svc.add_bank_account(ctx("resp_achats"), s, {
            "bank_name": "Banque Démo" if mf else "Demo Bank AG",
            "rib": rib_with_key(f"0100{i:02d}00000000{i:04d}") if mf else None,
            "iban": None if mf else "DE89370400440532013000", "currency": s.currency})
        sup_svc.verify_bank_account(ctx("daf"), acc, True, "Contre-appel effectué (démo)")
        sups[code] = s
    sup_svc.add_bank_account(ctx("agent_compta"), sups["F004"], {"bank_name": "Autre Banque", "rib": rib_with_key("080080000000000999")})
    db.add(SupplierContract(company_id=c.id, supplier_id=sups["F003"].id, reference="CT-MAINT-2026",
                            subject="Maintenance informatique mensuelle", start_date=t - timedelta(days=300),
                            end_date=t + timedelta(days=45), recurring_amount_ttc=Decimal("2380.000"), frequency_months=1,
                            next_due_date=t + timedelta(days=10), notice_days=60))
    db.add(SupplierEvaluation(company_id=c.id, supplier_id=sups["F002"].id, period="2026-T3", quality=2, delivery=2,
                              compliance=3, strategic_importance=3, supply_risk=4, comment="Retards répétés (démo)"))

    def attach(inv):
        db.add(Attachment(company_id=c.id, entity="facture", entity_id=inv.id, filename=f"{inv.supplier_number}.pdf",
                          content_type="application/pdf", size=0, sha256="0" * 64, storage_path="demo",
                          doc_type="facture (démo, fichier non fourni)", uploaded_by_id=users["agent_compta"].id))
        db.flush()
        inv.anomalies = inv_svc.run_controls(ctx("agent_compta"), inv)

    def po_flow(code, days_ago, lines, receive_ratio=Decimal(1), expected_delay=10):
        od = t - timedelta(days=days_ago)
        po = po_svc.create_order(ctx("resp_achats"), {"supplier_id": sups[code].id, "order_date": od,
                                                      "expected_date": od + timedelta(days=expected_delay), "lines": lines})
        po_svc.submit_order(ctx("resp_achats"), po)
        approver = "dg" if po.total_ttc * po.exchange_rate >= 50000 else "daf"
        po_svc.approve_order(ctx(approver), po, True)
        if receive_ratio > 0:
            po_svc.create_receipt(ctx("agent_compta" if code != "F003" else "resp_achats"), {
                "order_id": po.id, "receipt_date": od + timedelta(days=expected_delay + (5 if code == "F002" else 0)),
                "delivery_note_ref": f"BL-{po.number[-5:]}",
                "lines": [{"order_line_id": l.id, "qty_received": (l.quantity * receive_ratio).quantize(Decimal("1")) or 1,
                           "qty_rejected": 0} for l in po.lines]})
        return po

    def invoice_flow(code, po, days_ago, number, validate=True, price_factor=Decimal(1), qty_ratio=Decimal(1)):
        idate = t - timedelta(days=days_ago)
        inv = inv_svc.create_invoice(ctx("agent_compta"), {
            "supplier_id": sups[code].id, "supplier_number": number, "invoice_date": idate,
            "reception_date": idate + timedelta(days=2), "order_id": po.id if po else None,
            "lines": [{"order_line_id": l.id, "description": l.description, "item_ref": l.item_ref,
                       "quantity": (l.qty_received * qty_ratio) if po else l.quantity,
                       "unit_price": l.unit_price * price_factor, "tva_rate": l.tva_rate} for l in po.lines]})
        attach(inv)
        if validate:
            inv_svc.submit_invoice(ctx("agent_compta"), inv)
            levels = ["resp_compta", "daf", "dg"]
            for lvl in range(inv.required_levels):
                inv_svc.approve_invoice(ctx(levels[lvl]), inv)
        return inv

    def pay(code, invs_amounts, days_ago, method="virement", ref=None):
        p, _ = pay_svc.create_payment(ctx("tresorier"), {
            "supplier_id": sups[code].id, "method": method, "treasury_account_id": bank.id,
            "payment_date": t - timedelta(days=days_ago), "reference": ref,
            "allocations": [{"invoice_id": i.id, "amount": a} for i, a in invs_amounts]})
        pay_svc.submit_payment(ctx("tresorier"), p)
        pay_svc.approve_payment(ctx("daf"), p)
        if p.required_approvals > 1:
            pay_svc.approve_payment(ctx("dg"), p)
        pay_svc.execute_payment(ctx("tresorier"), p, t - timedelta(days=days_ago))
        return p

    L = lambda ref, desc, q, pu, tva=19, acc="6011": {"item_ref": ref, "description": desc, "quantity": Decimal(q),
                                                       "unit_price": Decimal(pu), "tva_rate": Decimal(tva), "account_code": acc}
    # 1. Alpha : achats réguliers, une facture réglée, une échue partiellement réglée, une non échue
    po1 = po_flow("F001", 200, [L("CIM-42", "Ciment CPJ 42.5 (tonne)", 40, "310.000"), L("FER-12", "Fer à béton Ø12 (tonne)", 5, "2950.000")])
    i1 = invoice_flow("F001", po1, 190, "A-2026-0412")
    pay("F001", [(i1, i1.total_ttc)], 120, "virement", "VIR-0001")
    po2 = po_flow("F001", 150, [L("CIM-42", "Ciment CPJ 42.5 (tonne)", 60, "315.000")])
    i2 = invoice_flow("F001", po2, 140, "A-2026-0588")
    pay("F001", [(i2, (i2.total_ttc / 2).quantize(Decimal("0.001")))], 30, "cheque", "CHQ-4471001")
    po3 = po_flow("F001", 25, [L("FER-12", "Fer à béton Ø12 (tonne)", 8, "3050.000")])
    invoice_flow("F001", po3, 15, "A-2026-0901")
    # 2. Bêta : facture échue de longue date + litige qualité
    po4 = po_flow("F002", 160, [L("CART-50", "Cartons 50x40", 5000, "1.150"), L("FILM", "Film étirable (rouleau)", 200, "18.500")])
    i4 = invoice_flow("F002", po4, 150, "B/26/0077")
    db.add(Dispute(company_id=c.id, number=next_number(db, c.id, "LT"), supplier_id=sups["F002"].id, invoice_id=i4.id,
                   kind="qualite", contested_amount=Decimal("1200.000"), reason="Lot de cartons humides (démo)",
                   opened_at=t - timedelta(days=60), owner_id=users["resp_achats"].id, status="en_cours",
                   created_by_id=users["resp_achats"].id))
    # 3. Bêta : commande approuvée non livrée (engagement)
    po_flow("F002", 10, [L("CART-30", "Cartons 30x20", 3000, "0.850")], receive_ratio=Decimal(0), expected_delay=20)
    # 4. Gamma : honoraires (RS 3 %) – facture en attente de validation, sans BC
    gi = inv_svc.create_invoice(ctx("agent_compta"), {
        "supplier_id": sups["F003"].id, "supplier_number": "GSI-2026-311", "invoice_date": t - timedelta(days=5),
        "lines": [{"description": "Maintenance informatique — mois en cours", "quantity": 1, "unit_price": Decimal("2000.000"),
                   "tva_rate": Decimal(19), "account_code": "6226"}]})
    attach(gi)
    inv_svc.submit_invoice(ctx("agent_compta"), gi)
    # 5. Europa (EUR) : commande d'équipement, facture validée en devise, non échue
    po5 = po_flow("F005", 100, [L("MCH-01", "Presse hydraulique", 1, "42000.000", 19, "2234")])
    invoice_flow("F005", po5, 90, "EU-26-1187")
    # 6. Delta : facture avec écart de prix (brouillon, anomalie bloquante)
    po6 = po_flow("F004", 12, [L("TRP", "Transport Tunis-Sfax (voyage)", 4, "450.000", 7, "6241")])
    invoice_flow("F004", po6, 3, "DT-889", validate=False, price_factor=Decimal("1.10"))
    # 7. Epsilon : avoir sur facture
    ei = inv_svc.create_invoice(ctx("agent_compta"), {
        "supplier_id": sups["F006"].id, "supplier_number": "EC-26-045", "invoice_date": t - timedelta(days=40),
        "lines": [{"description": "Mission conseil fiscal", "quantity": 1, "unit_price": Decimal("800.000"),
                   "tva_rate": Decimal(19), "account_code": "6226"}]})
    attach(ei)
    inv_svc.submit_invoice(ctx("agent_compta"), ei)
    inv_svc.approve_invoice(ctx("resp_compta"), ei, force=False) if not inv_svc.blocking(ei.anomalies) else \
        inv_svc.approve_invoice(ctx("daf"), ei, force=True, justification="Facture de service sans bon de commande — mission validée par la DG (démo)")
    av = inv_svc.create_invoice(ctx("agent_compta"), {
        "doc_type": "avoir", "supplier_id": sups["F006"].id, "supplier_number": "EC-AV-26-003",
        "invoice_date": t - timedelta(days=20), "origin_invoice_id": ei.id,
        "lines": [{"description": "Remise commerciale", "quantity": 1, "unit_price": Decimal("100.000"),
                   "tva_rate": Decimal(19), "account_code": "6226"}]})
    attach(av)
    inv_svc.submit_invoice(ctx("agent_compta"), av)
    inv_svc.approve_invoice(ctx("resp_compta"), av)
    inv_svc.allocate_credit(ctx("resp_compta"), av, ei, av.total_ttc, t - timedelta(days=19))
    # Relevé bancaire : le virement Alpha est débité
    from .models import Payment
    vir = db.scalar(select(Payment).where(Payment.company_id == c.id, Payment.reference == "VIR-0001"))
    pay_svc.import_statement(ctx("tresorier"), bank.id, [
        {"operation_date": vir.payment_date + timedelta(days=1), "label": "VIR EMIS ALPHA MATERIAUX",
         "reference": "VIR-0001", "amount": -(vir.cash_amount)},
        {"operation_date": t - timedelta(days=5), "label": "FRAIS BANCAIRES", "reference": None, "amount": Decimal("-12.500")}])
    db.flush()
    return c
