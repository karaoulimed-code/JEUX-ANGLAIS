import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Base):
    username: str
    password: str


class PasswordChangeIn(Base):
    current_password: str
    new_password: str


class UserIn(Base):
    username: str = Field(min_length=3, max_length=60)
    full_name: str
    email: str | None = None
    role: str
    password: str | None = None
    is_active: bool = True


class CustomerIn(Base):
    code: str | None = Field(default=None, max_length=30)
    legal_name: str = Field(min_length=2, max_length=200)
    trade_name: str | None = None
    tax_id: str | None = None
    rne_id: str | None = None
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str = "TN"
    phone: str | None = None
    email: str | None = None
    activity: str | None = None
    category_code: str | None = None
    sector_code: str | None = None
    zone_code: str | None = None
    group_code: str | None = None
    salesperson_id: int | None = None
    contact_name: str | None = None
    contact_function: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    bank_name: str | None = None
    bank_rib: str | None = None
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    payment_terms_label: str | None = None
    currency: str = "TND"
    credit_limit: Decimal = Decimal(0)
    max_exposure: Decimal = Decimal(0)
    notes: str | None = None


class InvoiceLineIn(Base):
    description: str
    quantity: Decimal = Decimal(1)
    unit_price: Decimal
    discount_pct: Decimal = Decimal(0)
    vat_code: str = "TVA19"


class InstallmentIn(Base):
    due_date: dt.date
    amount: Decimal


class InvoiceIn(Base):
    doc_type: str = "FACTURE"
    customer_id: int
    issue_date: dt.date
    due_date: dt.date | None = None
    currency: str | None = None
    exchange_rate: Decimal | None = None
    external_ref: str | None = None
    order_ref: str | None = None
    notes: str | None = None
    salesperson_id: int | None = None
    related_invoice_id: int | None = None
    apply_stamp: bool | None = None
    other_taxes: list[str] = []
    lines: list[InvoiceLineIn]
    installments: list[InstallmentIn] | None = None


class ClassifyIn(Base):
    classification: str
    reason: str


class AllocationIn(Base):
    invoice_id: int
    amount: Decimal


class PaymentIn(Base):
    customer_id: int
    method_id: int
    receipt_date: dt.date
    value_date: dt.date | None = None
    amount: Decimal
    currency: str = "TND"
    exchange_rate: Decimal | None = None
    reference: str | None = None
    bank_name: str | None = None
    drawer: str | None = None
    notes: str | None = None
    auto_allocate: bool = True
    allocations: list[AllocationIn] | None = None


class ManualAllocIn(Base):
    allocations: list[AllocationIn]
    date: dt.date | None = None


class StatusIn(Base):
    status: str
    date: dt.date
    reason: str | None = None


class ReasonIn(Base):
    reason: str


class DunningActionIn(Base):
    customer_id: int
    level_id: int | None = None
    action_type: str
    action_date: dt.date | None = None
    channel: str = "LETTRE"
    responsible_id: int | None = None
    result_code: str | None = None
    result: str | None = None
    promised_date: dt.date | None = None
    promised_amount: Decimal | None = None
    next_action: str | None = None
    next_action_date: dt.date | None = None
    comments: str | None = None
    invoice_ids: list[int] = []
    rendered_subject: str | None = None
    rendered_text: str | None = None


class PreviewIn(Base):
    customer_id: int
    template_id: int
    invoice_ids: list[int] | None = None


class ProvisionProposeIn(Base):
    as_of: dt.date
    method: str
    notes: str | None = None


class ProvisionLineIn(Base):
    rate: Decimal
    justification: str | None = None
    fiscal_deductible: bool | None = None


class DecisionIn(Base):
    approve: bool
    comment: str | None = None


class ApprovalIn(Base):
    kind: str
    entity_type: str
    entity_id: int
    payload: dict = {}
    reason: str


class IdsIn(Base):
    ids: list[int]


class ParamIn(Base):
    value: object
    valid_from: dt.date | None = None
    description: str | None = None
    source: str | None = None
    to_validate: bool | None = None
