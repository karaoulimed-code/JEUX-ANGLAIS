"""Modèle de données du poste fournisseurs.

Conventions :
- Chaque table métier porte `company_id` (prêt multi-entreprises / SaaS).
- Montants : Numeric(18,3) (le dinar compte 3 décimales : millimes).
- Taux de change : Numeric(18,6).
- Les documents validés ne sont jamais supprimés : ils sont annulés et contre-passés.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(18, 3)
Rate = Numeric(18, 6)
Pct = Numeric(9, 4)


def _now():
    return datetime.utcnow()


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(40))  # matricule fiscal
    address: Mapped[str | None] = mapped_column(String(300))
    base_currency: Mapped[str] = mapped_column(String(3), default="TND")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TenantMixin:
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ---------------------------------------------------------------- Sécurité
class User(TenantMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    language: Mapped[str] = mapped_column(String(5), default="fr")


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str | None] = mapped_column(String(64))


class AuditLog(Base):
    """Journal d'audit chaîné (chaque ligne contient l'empreinte de la précédente)."""
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    user_label: Mapped[str | None] = mapped_column(String(200))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(40))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


# ---------------------------------------------------------------- Paramétrage
class Setting(TenantMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("company_id", "key", name="uq_setting"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(500))
    label: Mapped[str | None] = mapped_column(String(300))


class TaxRate(TenantMixin, Base):
    """Taux paramétrables avec période de validité (TVA, retenue à la source, timbre...)."""
    __tablename__ = "tax_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # TVA | RS | TIMBRE | AUTRE
    code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(300))
    rate: Mapped[Decimal] = mapped_column(Pct, default=0)  # en %
    fixed_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    threshold: Mapped[Decimal] = mapped_column(Money, default=0)  # seuil d'application (TTC)
    account_code: Mapped[str | None] = mapped_column(String(20))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    legal_reference: Mapped[str | None] = mapped_column(String(300))
    verified_on: Mapped[date | None] = mapped_column(Date)
    to_verify: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AccountMapping(TenantMixin, Base):
    __tablename__ = "account_mappings"
    __table_args__ = (UniqueConstraint("company_id", "key", name="uq_account_mapping"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60))
    account_code: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(200))


class ExchangeRate(TenantMixin, Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("company_id", "currency", "rate_date", name="uq_fx"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(3))
    rate_date: Mapped[date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(Rate)  # 1 devise = rate TND
    source: Mapped[str | None] = mapped_column(String(100))


class Sequence(TenantMixin, Base):
    __tablename__ = "sequences"
    __table_args__ = (UniqueConstraint("company_id", "prefix", "year", name="uq_seq"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    prefix: Mapped[str] = mapped_column(String(10))
    year: Mapped[int] = mapped_column(Integer)
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class Attachment(TenantMixin, Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(500))
    doc_type: Mapped[str | None] = mapped_column(String(60))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# ---------------------------------------------------------------- Fournisseurs
class Supplier(TenantMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_supplier_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str | None] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(40), index=True)
    tax_id_normalized: Mapped[str | None] = mapped_column(String(40), index=True)
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2), default="TN")
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(100))
    supply_nature: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(20), default="regulier")
    status: Mapped[str] = mapped_column(String(20), default="en_attente")
    is_resident: Mapped[bool] = mapped_column(Boolean, default=True)
    vat_regime: Mapped[str] = mapped_column(String(20), default="assujetti")
    rs_code: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    payment_terms_type: Mapped[str] = mapped_column(String(20), default="net")  # net | fin_de_mois
    early_discount_pct: Mapped[Decimal] = mapped_column(Pct, default=0)
    early_discount_days: Mapped[int] = mapped_column(Integer, default=0)
    late_penalty_pct: Mapped[Decimal] = mapped_column(Pct, default=0)  # % annuel contractuel
    credit_limit: Mapped[Decimal | None] = mapped_column(Money)
    default_account: Mapped[str | None] = mapped_column(String(20))
    contract_terms: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)

    bank_accounts: Mapped[list["SupplierBankAccount"]] = relationship(back_populates="supplier")


class SupplierBankAccount(TenantMixin, Base):
    __tablename__ = "supplier_bank_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    bank_name: Mapped[str] = mapped_column(String(120))
    rib: Mapped[str | None] = mapped_column(String(40))
    iban: Mapped[str | None] = mapped_column(String(40))
    swift: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    status: Mapped[str] = mapped_column(String(20), default="a_verifier")  # a_verifier|verifie|rejete|remplace
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verification_note: Mapped[str | None] = mapped_column(String(300))
    supplier: Mapped[Supplier] = relationship(back_populates="bank_accounts")


class SupplierContract(TenantMixin, Base):
    __tablename__ = "supplier_contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    reference: Mapped[str] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(300))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[Decimal | None] = mapped_column(Money)
    recurring_amount_ttc: Mapped[Decimal] = mapped_column(Money, default=0)
    frequency_months: Mapped[int] = mapped_column(Integer, default=0)  # 0 = non récurrent
    next_due_date: Mapped[date | None] = mapped_column(Date)
    notice_days: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(20), default="actif")


class SupplierIncident(TenantMixin, Base):
    __tablename__ = "supplier_incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    incident_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(30))  # retard|qualite|quantite|prix|administratif|autre
    severity: Mapped[str] = mapped_column(String(10), default="moyenne")
    description: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class SupplierEvaluation(TenantMixin, Base):
    __tablename__ = "supplier_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    period: Mapped[str] = mapped_column(String(10))  # ex. 2026-T3
    quality: Mapped[int] = mapped_column(Integer)  # 1..5
    delivery: Mapped[int] = mapped_column(Integer)
    compliance: Mapped[int] = mapped_column(Integer)
    strategic_importance: Mapped[int] = mapped_column(Integer, default=3)
    supply_risk: Mapped[int] = mapped_column(Integer, default=3)  # risque de rupture 1..5
    comment: Mapped[str | None] = mapped_column(Text)
    evaluated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# ---------------------------------------------------------------- Achats
class PurchaseRequest(TenantMixin, Base):
    __tablename__ = "purchase_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30))
    request_date: Mapped[date] = mapped_column(Date)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    department: Mapped[str | None] = mapped_column(String(100))
    justification: Mapped[str | None] = mapped_column(Text)
    suggested_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    estimated_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    needed_by: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="brouillon")
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_comment: Mapped[str | None] = mapped_column(String(500))
    lines: Mapped[list["PurchaseRequestLine"]] = relationship(cascade="all, delete-orphan")


class PurchaseRequestLine(Base):
    __tablename__ = "purchase_request_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("purchase_requests.id"), index=True)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Money)
    estimated_unit_price: Mapped[Decimal] = mapped_column(Money, default=0)


class PurchaseOrder(TenantMixin, Base):
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_requests.id"))
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=1)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    payment_terms_type: Mapped[str] = mapped_column(String(20), default="net")
    total_ht: Mapped[Decimal] = mapped_column(Money, default=0)
    total_tva: Mapped[Decimal] = mapped_column(Money, default=0)
    total_ttc: Mapped[Decimal] = mapped_column(Money, default=0)
    status: Mapped[str] = mapped_column(String(25), default="brouillon")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        cascade="all, delete-orphan", order_by="PurchaseOrderLine.id")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    item_ref: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Money)
    unit_price: Mapped[Decimal] = mapped_column(Money)
    tva_rate: Mapped[Decimal] = mapped_column(Pct, default=19)
    account_code: Mapped[str | None] = mapped_column(String(20))
    qty_received: Mapped[Decimal] = mapped_column(Money, default=0)
    qty_invoiced: Mapped[Decimal] = mapped_column(Money, default=0)


class GoodsReceipt(TenantMixin, Base):
    __tablename__ = "goods_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    receipt_date: Mapped[date] = mapped_column(Date)
    delivery_note_ref: Mapped[str | None] = mapped_column(String(60))
    received_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="validee")
    notes: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[list["GoodsReceiptLine"]] = relationship(cascade="all, delete-orphan")


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id"), index=True)
    order_line_id: Mapped[int] = mapped_column(ForeignKey("purchase_order_lines.id"), index=True)
    qty_received: Mapped[Decimal] = mapped_column(Money)
    qty_rejected: Mapped[Decimal] = mapped_column(Money, default=0)
    comment: Mapped[str | None] = mapped_column(String(300))


# ---------------------------------------------------------------- Factures
class Invoice(TenantMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (Index("ix_invoice_supplier_number", "company_id", "supplier_id", "number_normalized"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    internal_ref: Mapped[str] = mapped_column(String(30), index=True)
    doc_type: Mapped[str] = mapped_column(String(15), default="facture")  # facture|avoir|acompte
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    supplier_number: Mapped[str] = mapped_column(String(60))
    number_normalized: Mapped[str] = mapped_column(String(60))
    invoice_date: Mapped[date] = mapped_column(Date)
    reception_date: Mapped[date | None] = mapped_column(Date)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    receipt_refs: Mapped[str | None] = mapped_column(String(200))
    origin_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))  # avoir -> facture
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=1)
    total_ht: Mapped[Decimal] = mapped_column(Money, default=0)
    total_tva: Mapped[Decimal] = mapped_column(Money, default=0)
    stamp_duty: Mapped[Decimal] = mapped_column(Money, default=0)
    other_taxes: Mapped[Decimal] = mapped_column(Money, default=0)
    total_ttc: Mapped[Decimal] = mapped_column(Money, default=0)
    declared_total_ttc: Mapped[Decimal | None] = mapped_column(Money)
    rs_code: Mapped[str | None] = mapped_column(String(40))
    rs_rate: Mapped[Decimal] = mapped_column(Pct, default=0)
    rs_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    net_to_pay: Mapped[Decimal] = mapped_column(Money, default=0)
    total_ttc_tnd: Mapped[Decimal] = mapped_column(Money, default=0)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    workflow_status: Mapped[str] = mapped_column(String(25), default="brouillon")
    matching_status: Mapped[str] = mapped_column(String(20), default="non_controle")
    anomalies: Mapped[list | None] = mapped_column(JSON)
    required_levels: Mapped[int] = mapped_column(Integer, default=1)
    approved_levels: Mapped[int] = mapped_column(Integer, default=0)
    forced: Mapped[bool] = mapped_column(Boolean, default=False)
    force_justification: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    cancelled_at: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(20), default="saisie")  # saisie|import|ocr
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)
    lines: Mapped[list["InvoiceLine"]] = relationship(cascade="all, delete-orphan", order_by="InvoiceLine.id")
    supplier: Mapped[Supplier] = relationship()


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    order_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_lines.id"))
    item_ref: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Money)
    unit_price: Mapped[Decimal] = mapped_column(Money)
    tva_rate: Mapped[Decimal] = mapped_column(Pct, default=19)
    amount_ht: Mapped[Decimal] = mapped_column(Money)
    amount_tva: Mapped[Decimal] = mapped_column(Money)
    account_code: Mapped[str | None] = mapped_column(String(20))


class InvoiceApproval(TenantMixin, Base):
    __tablename__ = "invoice_approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(15))  # approuve|rejete|force
    comment: Mapped[str | None] = mapped_column(Text)


class CreditAllocation(TenantMixin, Base):
    """Imputation d'un avoir (lettrage) ou d'une facture d'acompte sur une facture."""
    __tablename__ = "credit_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # avoir|acompte
    source_invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    target_invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)  # en devise de facture, TTC
    allocation_date: Mapped[date] = mapped_column(Date)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------- Trésorerie / règlements
class TreasuryAccount(TenantMixin, Base):
    __tablename__ = "treasury_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10), default="banque")  # banque|caisse
    bank_name: Mapped[str | None] = mapped_column(String(120))
    rib: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    account_code: Mapped[str] = mapped_column(String(20), default="532")
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=0)
    opening_date: Mapped[date | None] = mapped_column(Date)
    authorized_overdraft: Mapped[Decimal] = mapped_column(Money, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PaymentRun(TenantMixin, Base):
    __tablename__ = "payment_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30))
    planned_date: Mapped[date] = mapped_column(Date)
    treasury_account_id: Mapped[int | None] = mapped_column(ForeignKey("treasury_accounts.id"))
    status: Mapped[str] = mapped_column(String(20), default="brouillon")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Payment(TenantMixin, Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("payment_runs.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="reglement")  # reglement|avance
    method: Mapped[str] = mapped_column(String(15))  # virement|cheque|especes|effet|autre
    treasury_account_id: Mapped[int | None] = mapped_column(ForeignKey("treasury_accounts.id"))
    supplier_bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_bank_accounts.id"))
    payment_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)  # échéance d'un effet
    reference: Mapped[str | None] = mapped_column(String(60))  # n° chèque / effet / ordre
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=1)
    cash_amount: Mapped[Decimal] = mapped_column(Money)  # montant décaissé
    rs_amount: Mapped[Decimal] = mapped_column(Money, default=0)  # retenue à la source
    status: Mapped[str] = mapped_column(String(20), default="brouillon")
    # brouillon|a_approuver|approuve|emis|debite|rejete|annule
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    prepared_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    second_approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    executed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cleared_date: Mapped[date | None] = mapped_column(Date)
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    rejected_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    allocations: Mapped[list["PaymentAllocation"]] = relationship(cascade="all, delete-orphan")
    supplier: Mapped[Supplier] = relationship()


class PaymentAllocation(TenantMixin, Base):
    __tablename__ = "payment_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)  # part de facture soldée (TTC, devise facture)
    rs_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    allocation_date: Mapped[date] = mapped_column(Date)
    fx_difference_tnd: Mapped[Decimal] = mapped_column(Money, default=0)  # >0 perte, <0 gain
    deferred: Mapped[bool] = mapped_column(Boolean, default=False)  # affectation ultérieure au décaissement
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)


class BankStatementLine(TenantMixin, Base):
    __tablename__ = "bank_statement_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    treasury_account_id: Mapped[int] = mapped_column(ForeignKey("treasury_accounts.id"), index=True)
    operation_date: Mapped[date] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String(300))
    reference: Mapped[str | None] = mapped_column(String(60))
    amount: Mapped[Decimal] = mapped_column(Money)  # négatif = débit
    matched_payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    import_batch: Mapped[str | None] = mapped_column(String(40))


# ---------------------------------------------------------------- Litiges
class Dispute(TenantMixin, Base):
    __tablename__ = "disputes"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    kind: Mapped[str] = mapped_column(String(25))
    # prix|quantite|qualite|retour|retard_livraison|facture_contestee|penalite|autre
    contested_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    returned_quantity: Mapped[Decimal | None] = mapped_column(Money)
    penalty_amount: Mapped[Decimal | None] = mapped_column(Money)
    reason: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[date] = mapped_column(Date)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(15), default="ouvert")  # ouvert|en_cours|resolu|clos
    progress_notes: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String(30))  # avoir_obtenu|rejete|accord_partiel|paye
    closed_at: Mapped[date | None] = mapped_column(Date)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# ---------------------------------------------------------------- Comptabilité
class JournalEntry(TenantMixin, Base):
    __tablename__ = "journal_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    journal: Mapped[str] = mapped_column(String(10))  # ACH|REG|OD
    number: Mapped[str] = mapped_column(String(30))
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    label: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(15), default="proposee")  # proposee|validee
    validated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)
    reversal_of_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime)
    lines: Mapped[list["JournalLine"]] = relationship(cascade="all, delete-orphan", order_by="JournalLine.id")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), index=True)
    account_code: Mapped[str] = mapped_column(String(20), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    label: Mapped[str] = mapped_column(String(300))
    debit: Mapped[Decimal] = mapped_column(Money, default=0)
    credit: Mapped[Decimal] = mapped_column(Money, default=0)


__all__ = [n for n in dir() if n[0].isupper()]
_ = func  # noqa
