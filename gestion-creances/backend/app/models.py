"""Modèle de données unique du poste clients.

Toutes les tables partagent la même base : une facture, un règlement ou une
affectation modifie immédiatement les soldes, la balance âgée, le risque et
les prévisions, car ces derniers sont calculés à partir des mêmes lignes.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(18, 3)
Rate = Numeric(18, 6)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, server_default=func.now())


# --------------------------------------------------------------------------- sécurité
class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class AuditLog(Base):
    """Journal d'audit chaîné (chaque ligne contient l'empreinte de la précédente).

    Un déclencheur PostgreSQL interdit UPDATE et DELETE : même un administrateur
    applicatif ne peut pas le modifier. Toute altération directe en base casse la
    chaîne d'empreintes et est détectée par /audit/verify.
    """
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(40), index=True)
    details: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


# --------------------------------------------------------------------------- paramétrage
class Parameter(Base):
    """Moteur de paramétrage daté : une valeur s'applique à partir de valid_from."""
    __tablename__ = "parameters"
    __table_args__ = (UniqueConstraint("key", "valid_from"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[dict | list | str | int | float | None] = mapped_column(JSON)
    valid_from: Mapped[dt.date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)        # texte légal / référence
    to_validate: Mapped[bool] = mapped_column(Boolean, default=False)  # à valider par l'expert-comptable
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TaxRate(Base):
    __tablename__ = "tax_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))  # TVA | TIMBRE | AUTRE
    rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))         # en %
    fixed_amount: Mapped[Decimal | None] = mapped_column(Money)          # montant fixe par facture
    account_code: Mapped[str | None] = mapped_column(String(20))
    in_vat_base: Mapped[bool] = mapped_column(Boolean, default=False)  # ex. FODEC inclus dans l'assiette TVA
    valid_from: Mapped[dt.date] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str | None] = mapped_column(Text)
    to_validate: Mapped[bool] = mapped_column(Boolean, default=False)


class Currency(Base):
    __tablename__ = "currencies"
    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    label: Mapped[str] = mapped_column(String(60))
    decimals: Mapped[int] = mapped_column(Integer, default=3)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("currency", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(ForeignKey("currencies.code"))
    date: Mapped[dt.date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(Rate)  # TND pour 1 unité de devise
    source: Mapped[str | None] = mapped_column(String(60))


class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))  # ESPECES|CHEQUE|VIREMENT|EFFET|RETENUE_SOURCE|AUTRE
    requires_clearing: Mapped[bool] = mapped_column(Boolean, default=False)
    account_code: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReferenceValue(Base):
    """Listes de valeurs : catégories, secteurs, zones, groupes de clients."""
    __tablename__ = "reference_values"
    __table_args__ = (UniqueConstraint("kind", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # CATEGORY|SECTOR|ZONE|GROUP
    code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Sequence(Base):
    __tablename__ = "sequences"
    __table_args__ = (UniqueConstraint("key", "year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(20))
    year: Mapped[int] = mapped_column(Integer)
    next_value: Mapped[int] = mapped_column(Integer, default=1)


# --------------------------------------------------------------------------- clients
class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(200), index=True)
    trade_name: Mapped[str | None] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(40), index=True)   # matricule fiscal
    rne_id: Mapped[str | None] = mapped_column(String(40))               # identifiant RNE
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    postal_code: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(2), default="TN")
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(150))
    activity: Mapped[str | None] = mapped_column(String(200))
    category_code: Mapped[str | None] = mapped_column(String(40))
    sector_code: Mapped[str | None] = mapped_column(String(40))
    zone_code: Mapped[str | None] = mapped_column(String(40))
    group_code: Mapped[str | None] = mapped_column(String(40))
    salesperson_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    contact_name: Mapped[str | None] = mapped_column(String(150))
    contact_function: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    contact_email: Mapped[str | None] = mapped_column(String(150))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_rib: Mapped[str | None] = mapped_column(String(40))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    payment_terms_label: Mapped[str | None] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    credit_limit: Mapped[Decimal] = mapped_column(Money, default=0)     # plafond de créances ouvertes (TND)
    max_exposure: Mapped[Decimal] = mapped_column(Money, default=0)     # encours max : créances + effets/chèques non encaissés
    status: Mapped[str] = mapped_column(String(20), default="ACTIF")    # ACTIF|BLOQUE|ARCHIVE
    in_litigation: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_class: Mapped[str | None] = mapped_column(String(20))
    risk_computed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    salesperson: Mapped[User | None] = relationship(foreign_keys=[salesperson_id])


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(400))
    description: Mapped[str | None] = mapped_column(String(255))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# --------------------------------------------------------------------------- factures
class Invoice(TimestampMixin, Base):
    """Facture ou avoir (doc_type). Une pièce validée ne peut plus être modifiée :
    toute correction passe par un avoir (déclencheur PostgreSQL de protection)."""
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("doc_type", "number", name="uq_invoice_number"),
        CheckConstraint("doc_type in ('FACTURE','AVOIR')"),
        CheckConstraint("lifecycle in ('BROUILLON','VALIDEE')"),
        CheckConstraint("classification in ('NORMALE','LITIGIEUSE','DOUTEUSE','IRRECOUVRABLE')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(10), default="FACTURE")
    number: Mapped[str | None] = mapped_column(String(40), index=True)
    external_ref: Mapped[str | None] = mapped_column(String(60), index=True)
    source: Mapped[str] = mapped_column(String(20), default="SAISIE")  # SAISIE|IMPORT|EXTERNE
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    issue_date: Mapped[dt.date] = mapped_column(Date, index=True)
    due_date: Mapped[dt.date] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=1)
    total_ht: Mapped[Decimal] = mapped_column(Money, default=0)
    total_vat: Mapped[Decimal] = mapped_column(Money, default=0)
    total_other_taxes: Mapped[Decimal] = mapped_column(Money, default=0)
    total_ttc: Mapped[Decimal] = mapped_column(Money, default=0)
    total_ttc_tnd: Mapped[Decimal] = mapped_column(Money, default=0)
    total_ht_tnd: Mapped[Decimal] = mapped_column(Money, default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=0)      # pour un avoir : montant imputé
    balance: Mapped[Decimal] = mapped_column(Money, default=0)          # reste dû (ou reste à imputer)
    lifecycle: Mapped[str] = mapped_column(String(12), default="BROUILLON")
    classification: Mapped[str] = mapped_column(String(15), default="NORMALE")
    classification_reason: Mapped[str | None] = mapped_column(Text)
    classified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    related_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))
    salesperson_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    order_ref: Mapped[str | None] = mapped_column(String(60))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.position")
    taxes: Mapped[list["InvoiceTax"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    installments: Mapped[list["Installment"]] = relationship(back_populates="invoice", cascade="all, delete-orphan", order_by="Installment.seq")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=0)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(7, 3), default=0)
    vat_code: Mapped[str | None] = mapped_column(String(30))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=0)
    amount_ht: Mapped[Decimal] = mapped_column(Money, default=0)
    vat_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class InvoiceTax(Base):
    """Récapitulatif figé des taxes de la pièce (TVA par taux, timbre, autres)."""
    __tablename__ = "invoice_taxes"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    base: Mapped[Decimal] = mapped_column(Money, default=0)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    amount: Mapped[Decimal] = mapped_column(Money, default=0)
    account_code: Mapped[str | None] = mapped_column(String(20))
    invoice: Mapped[Invoice] = relationship(back_populates="taxes")


class Installment(Base):
    """Échéance. La balance âgée et les relances travaillent au niveau de l'échéance."""
    __tablename__ = "installments"
    __table_args__ = (UniqueConstraint("invoice_id", "seq"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1)
    due_date: Mapped[dt.date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    amount_tnd: Mapped[Decimal] = mapped_column(Money)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    paid_amount_tnd: Mapped[Decimal] = mapped_column(Money, default=0)
    invoice: Mapped[Invoice] = relationship(back_populates="installments")


# --------------------------------------------------------------------------- encaissements
class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0"),
        CheckConstraint("status in ('EN_PORTEFEUILLE','REMIS','ENCAISSE','REJETE','ANNULE')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    method_id: Mapped[int] = mapped_column(ForeignKey("payment_methods.id"))
    method_kind: Mapped[str] = mapped_column(String(20))
    receipt_date: Mapped[dt.date] = mapped_column(Date, index=True)
    value_date: Mapped[dt.date | None] = mapped_column(Date)     # date d'encaissement prévue / échéance de l'effet
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=1)
    amount_tnd: Mapped[Decimal] = mapped_column(Money)
    allocated_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    reference: Mapped[str | None] = mapped_column(String(80))    # n° chèque, référence virement, n° certificat RS
    bank_name: Mapped[str | None] = mapped_column(String(100))
    drawer: Mapped[str | None] = mapped_column(String(150))      # tireur
    status: Mapped[str] = mapped_column(String(20), default="ENCAISSE")
    deposited_date: Mapped[dt.date | None] = mapped_column(Date)
    cleared_date: Mapped[dt.date | None] = mapped_column(Date)
    rejected_date: Mapped[dt.date | None] = mapped_column(Date)
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    cancelled_date: Mapped[dt.date | None] = mapped_column(Date)
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer] = relationship()
    method: Mapped[PaymentMethod] = relationship()


class Adjustment(TimestampMixin, Base):
    """Opération diverse au crédit du client : écart de règlement, passage en perte
    (créance irrécouvrable), abandon de créance."""
    __tablename__ = "adjustments"
    __table_args__ = (CheckConstraint("amount > 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(25))  # ECART_REGLEMENT|PASSAGE_PERTE|ABANDON_CREANCE
    date: Mapped[dt.date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="TND")
    exchange_rate: Mapped[Decimal] = mapped_column(Rate, default=1)
    amount_tnd: Mapped[Decimal] = mapped_column(Money)
    allocated_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    reason: Mapped[str] = mapped_column(Text)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Allocation(Base):
    """Lettrage : affectation d'un crédit (règlement, avoir ou OD) à une échéance."""
    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint("amount > 0"),
        CheckConstraint(
            "(CASE WHEN payment_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN credit_note_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN adjustment_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_allocation_one_source",
        ),
        Index("ix_alloc_active", "installment_id", "reversed_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    installment_id: Mapped[int] = mapped_column(ForeignKey("installments.id"), index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), index=True)
    credit_note_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    adjustment_id: Mapped[int | None] = mapped_column(ForeignKey("adjustments.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)           # devise de la facture
    amount_tnd: Mapped[Decimal] = mapped_column(Money)       # au cours de la facture
    source_amount_tnd: Mapped[Decimal] = mapped_column(Money)  # au cours du règlement
    fx_difference_tnd: Mapped[Decimal] = mapped_column(Money, default=0)  # >0 gain de change
    allocation_date: Mapped[dt.date] = mapped_column(Date, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    reversed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_date: Mapped[dt.date | None] = mapped_column(Date)
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reversal_reason: Mapped[str | None] = mapped_column(String(255))

    installment: Mapped[Installment] = relationship()
    invoice: Mapped[Invoice] = relationship(foreign_keys=[invoice_id])


# --------------------------------------------------------------------------- recouvrement
class DunningTemplate(Base):
    __tablename__ = "dunning_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    channel: Mapped[str] = mapped_column(String(20))  # LETTRE|EMAIL|SMS
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DunningLevel(Base):
    __tablename__ = "dunning_levels"
    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[int] = mapped_column(Integer, unique=True)
    code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(120))
    days_after_due: Mapped[int] = mapped_column(Integer)
    min_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("dunning_templates.id"))
    escalate_to_legal: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DunningAction(Base):
    __tablename__ = "dunning_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    level_id: Mapped[int | None] = mapped_column(ForeignKey("dunning_levels.id"))
    action_type: Mapped[str] = mapped_column(String(30))
    action_date: Mapped[dt.date] = mapped_column(Date, index=True)
    channel: Mapped[str] = mapped_column(String(20))   # LETTRE|EMAIL|TELEPHONE|VISITE|SMS|HUISSIER|AVOCAT
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    result_code: Mapped[str | None] = mapped_column(String(30))
    result: Mapped[str | None] = mapped_column(Text)
    promised_date: Mapped[dt.date | None] = mapped_column(Date)
    promised_amount: Mapped[Decimal | None] = mapped_column(Money)
    next_action: Mapped[str | None] = mapped_column(String(200))
    next_action_date: Mapped[dt.date | None] = mapped_column(Date, index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    amount_due_tnd: Mapped[Decimal] = mapped_column(Money, default=0)
    rendered_subject: Mapped[str | None] = mapped_column(String(250))
    rendered_text: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    invoices: Mapped[list["DunningActionInvoice"]] = relationship(cascade="all, delete-orphan")


class DunningActionInvoice(Base):
    __tablename__ = "dunning_action_invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    action_id: Mapped[int] = mapped_column(ForeignKey("dunning_actions.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    balance_at_action: Mapped[Decimal] = mapped_column(Money, default=0)


# --------------------------------------------------------------------------- risque & provisions
class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    as_of: Mapped[dt.date] = mapped_column(Date)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    score: Mapped[int] = mapped_column(Integer)
    risk_class: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict] = mapped_column(JSON)


class ProvisionCampaign(Base):
    __tablename__ = "provision_campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[dt.date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(10))  # NCT|IFRS9
    status: Mapped[str] = mapped_column(String(15), default="PROPOSEE")  # PROPOSEE|VALIDEE|REJETEE
    notes: Mapped[str | None] = mapped_column(Text)
    total_amount_tnd: Mapped[Decimal] = mapped_column(Money, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    lines: Mapped[list["Provision"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class Provision(Base):
    __tablename__ = "provisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("provision_campaigns.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    method: Mapped[str] = mapped_column(String(10))
    bucket: Mapped[str | None] = mapped_column(String(20))
    days_overdue: Mapped[int] = mapped_column(Integer, default=0)
    outstanding_tnd: Mapped[Decimal] = mapped_column(Money)
    base_tnd: Mapped[Decimal] = mapped_column(Money)
    rate: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    suggested_rate: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    amount_tnd: Mapped[Decimal] = mapped_column(Money)
    previous_amount_tnd: Mapped[Decimal] = mapped_column(Money, default=0)
    movement_tnd: Mapped[Decimal] = mapped_column(Money, default=0)  # >0 dotation, <0 reprise
    justification: Mapped[str | None] = mapped_column(Text)
    fiscal_deductible: Mapped[bool] = mapped_column(Boolean, default=False)
    fiscal_note: Mapped[str | None] = mapped_column(Text)
    campaign: Mapped[ProvisionCampaign] = relationship(back_populates="lines")


# --------------------------------------------------------------------------- comptabilité
class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (CheckConstraint("status in ('PROPOSEE','VALIDEE','EXPORTEE','REJETEE')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    journal: Mapped[str] = mapped_column(String(10))  # VT|ENC|OD
    entry_date: Mapped[dt.date] = mapped_column(Date, index=True)
    label: Mapped[str] = mapped_column(String(250))
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[int] = mapped_column(Integer)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(10), default="PROPOSEE")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    export_batch: Mapped[str | None] = mapped_column(String(40))
    exported_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    lines: Mapped[list["JournalLine"]] = relationship(back_populates="entry", cascade="all, delete-orphan", order_by="JournalLine.id")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (CheckConstraint("debit >= 0 AND credit >= 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id", ondelete="CASCADE"), index=True)
    account: Mapped[str] = mapped_column(String(20))
    aux_account: Mapped[str | None] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(250))
    debit: Mapped[Decimal] = mapped_column(Money, default=0)
    credit: Mapped[Decimal] = mapped_column(Money, default=0)
    entry: Mapped[JournalEntry] = relationship(back_populates="lines")


# --------------------------------------------------------------------------- contrôle interne
class ApprovalRequest(Base):
    """Validation « à quatre yeux » des opérations sensibles."""
    __tablename__ = "approval_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # CREDIT_LIMIT|CLASSIFICATION|WRITE_OFF|PAYMENT_CANCEL
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(15), default="EN_ATTENTE")  # EN_ATTENTE|APPROUVEE|REJETEE
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)
