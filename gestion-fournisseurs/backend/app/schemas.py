"""Schémas d'entrée de l'API (validation) et sérialisation générique."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import inspect as sa_inspect


def ser(obj, **extra) -> dict:
    if obj is None:
        return None
    d = {c.key: getattr(obj, c.key) for c in sa_inspect(obj).mapper.column_attrs}
    d.pop("password_hash", None)
    d.update(extra)
    return d


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(In):
    email: str
    password: str


class UserIn(In):
    email: EmailStr
    full_name: str
    role: str
    password: str
    language: str = "fr"


class UserUpdate(In):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    language: str | None = None


class PasswordChange(In):
    old_password: str
    new_password: str


class SupplierIn(In):
    code: str = Field(min_length=1, max_length=20)
    legal_name: str = Field(min_length=2)
    trade_name: str | None = None
    tax_id: str | None = None
    address: str | None = None
    city: str | None = None
    country: str = "TN"
    phone: str | None = None
    email: str | None = None
    contact_name: str | None = None
    sector: str | None = None
    supply_nature: str | None = None
    category: Literal["strategique", "regulier", "occasionnel", "critique", "a_risque"] = "regulier"
    is_resident: bool = True
    vat_regime: Literal["assujetti", "non_assujetti", "exonere", "forfaitaire"] = "assujetti"
    rs_code: str | None = None
    currency: str = "TND"
    payment_terms_days: int = Field(30, ge=0, le=365)
    payment_terms_type: Literal["net", "fin_de_mois"] = "net"
    early_discount_pct: Decimal = Decimal(0)
    early_discount_days: int = 0
    late_penalty_pct: Decimal = Decimal(0)
    credit_limit: Decimal | None = None
    default_account: str | None = None
    contract_terms: str | None = None
    notes: str | None = None


class SupplierUpdate(SupplierIn):
    model_config = ConfigDict(extra="forbid")
    code: str | None = None  # type: ignore[assignment]
    legal_name: str | None = None  # type: ignore[assignment]


class StatusIn(In):
    status: str
    comment: str | None = None


class BankAccountIn(In):
    bank_name: str
    rib: str | None = None
    iban: str | None = None
    swift: str | None = None
    currency: str = "TND"


class VerifyIn(In):
    accept: bool
    note: str | None = None


class ContractIn(In):
    reference: str
    subject: str
    start_date: date
    end_date: date | None = None
    total_amount: Decimal | None = None
    recurring_amount_ttc: Decimal = Decimal(0)
    frequency_months: int = 0
    next_due_date: date | None = None
    notice_days: int = 60


class IncidentIn(In):
    incident_date: date
    kind: Literal["retard", "qualite", "quantite", "prix", "administratif", "autre"]
    severity: Literal["faible", "moyenne", "grave"] = "moyenne"
    description: str


class EvaluationIn(In):
    period: str
    quality: int = Field(ge=1, le=5)
    delivery: int = Field(ge=1, le=5)
    compliance: int = Field(ge=1, le=5)
    strategic_importance: int = Field(3, ge=1, le=5)
    supply_risk: int = Field(3, ge=1, le=5)
    comment: str | None = None


class PRLineIn(In):
    description: str
    quantity: Decimal = Field(gt=0)
    estimated_unit_price: Decimal = Decimal(0)


class PRIn(In):
    request_date: date
    department: str | None = None
    justification: str | None = None
    suggested_supplier_id: int | None = None
    needed_by: date | None = None
    lines: list[PRLineIn]


class DecisionIn(In):
    approve: bool
    comment: str | None = None


class POLineIn(In):
    item_ref: str | None = None
    description: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    tva_rate: Decimal = Decimal(19)
    account_code: str | None = None


class POIn(In):
    supplier_id: int
    request_id: int | None = None
    order_date: date
    expected_date: date | None = None
    currency: str | None = None
    payment_terms_days: int | None = None
    payment_terms_type: Literal["net", "fin_de_mois"] | None = None
    notes: str | None = None
    lines: list[POLineIn]


class POUpdate(In):
    expected_date: date | None = None
    notes: str | None = None
    payment_terms_days: int | None = None
    lines: list[POLineIn] | None = None


class ReasonIn(In):
    reason: str = Field(min_length=3)


class GRLineIn(In):
    order_line_id: int
    qty_received: Decimal
    qty_rejected: Decimal = Decimal(0)
    comment: str | None = None


class GRIn(In):
    order_id: int
    receipt_date: date
    delivery_note_ref: str | None = None
    notes: str | None = None
    lines: list[GRLineIn]


class InvLineIn(In):
    order_line_id: int | None = None
    item_ref: str | None = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tva_rate: Decimal = Decimal(19)
    amount_ht: Decimal | None = None
    amount_tva: Decimal | None = None
    account_code: str | None = None


class InvoiceIn(In):
    doc_type: Literal["facture", "avoir", "acompte"] = "facture"
    supplier_id: int
    supplier_number: str = Field(min_length=1)
    invoice_date: date
    reception_date: date | None = None
    order_id: int | None = None
    receipt_refs: str | None = None
    origin_invoice_id: int | None = None
    currency: str | None = None
    exchange_rate: Decimal | None = None
    stamp_duty: Decimal | None = None
    other_taxes: Decimal | None = None
    declared_total_ttc: Decimal | None = None
    rs_code: str | None = None
    due_date: date | None = None
    description: str | None = None
    lines: list[InvLineIn]


class InvoiceUpdate(In):
    supplier_number: str | None = None
    invoice_date: date | None = None
    reception_date: date | None = None
    order_id: int | None = None
    receipt_refs: str | None = None
    origin_invoice_id: int | None = None
    exchange_rate: Decimal | None = None
    stamp_duty: Decimal | None = None
    other_taxes: Decimal | None = None
    declared_total_ttc: Decimal | None = None
    rs_code: str | None = None
    due_date: date | None = None
    description: str | None = None
    lines: list[InvLineIn] | None = None


class ApproveIn(In):
    comment: str | None = None
    force: bool = False
    justification: str | None = None


class CreditAllocIn(In):
    source_invoice_id: int
    target_invoice_id: int
    amount: Decimal
    allocation_date: date


class AllocIn(In):
    invoice_id: int
    amount: Decimal


class PaymentIn(In):
    supplier_id: int
    kind: Literal["reglement", "avance"] = "reglement"
    method: Literal["virement", "cheque", "especes", "effet", "autre"]
    treasury_account_id: int | None = None
    supplier_bank_account_id: int | None = None
    payment_date: date
    due_date: date | None = None
    reference: str | None = None
    currency: str | None = None
    allocations: list[AllocIn] = []
    unallocated_amount: Decimal | None = None
    advance_rs_amount: Decimal | None = None
    notes: str | None = None


class ExecuteIn(In):
    execution_date: date | None = None
    reference: str | None = None


class RejectIn(In):
    reason: str = Field(min_length=3)
    rejection_date: date | None = None


class LaterAllocIn(In):
    invoice_id: int
    amount: Decimal
    allocation_date: date


class RunItemIn(In):
    invoice_id: int
    amount: Decimal | None = None


class RunIn(In):
    planned_date: date
    treasury_account_id: int | None = None
    method: Literal["virement", "cheque", "especes", "effet", "autre"] = "virement"
    notes: str | None = None
    items: list[RunItemIn]


class TreasuryIn(In):
    name: str
    kind: Literal["banque", "caisse"] = "banque"
    bank_name: str | None = None
    rib: str | None = None
    currency: str = "TND"
    account_code: str = "532"
    opening_balance: Decimal = Decimal(0)
    opening_date: date | None = None
    authorized_overdraft: Decimal = Decimal(0)


class StatementLineIn(In):
    operation_date: date
    label: str
    reference: str | None = None
    amount: Decimal


class StatementIn(In):
    treasury_account_id: int
    lines: list[StatementLineIn]


class MatchIn(In):
    statement_line_id: int
    payment_id: int


class DisputeIn(In):
    supplier_id: int
    invoice_id: int | None = None
    order_id: int | None = None
    kind: Literal["prix", "quantite", "qualite", "retour", "retard_livraison", "facture_contestee", "penalite", "autre"]
    contested_amount: Decimal = Decimal(0)
    returned_quantity: Decimal | None = None
    penalty_amount: Decimal | None = None
    reason: str
    opened_at: date
    owner_id: int | None = None


class DisputeUpdate(In):
    status: Literal["ouvert", "en_cours", "resolu", "clos"] | None = None
    progress_notes: str | None = None
    decision: str | None = None
    outcome: Literal["avoir_obtenu", "rejete", "accord_partiel", "paye", "penalite_appliquee"] | None = None
    contested_amount: Decimal | None = None
    owner_id: int | None = None


class SettingIn(In):
    value: str


class TaxRateIn(In):
    kind: Literal["TVA", "RS", "TIMBRE", "AUTRE"]
    code: str
    label: str
    rate: Decimal = Decimal(0)
    fixed_amount: Decimal = Decimal(0)
    threshold: Decimal = Decimal(0)
    account_code: str | None = None
    valid_from: date
    valid_to: date | None = None
    legal_reference: str | None = None
    verified_on: date | None = None
    to_verify: bool = True
    is_active: bool = True


class AccountMapIn(In):
    account_code: str
    label: str | None = None


class FxIn(In):
    currency: str = Field(min_length=3, max_length=3)
    rate_date: date
    rate: Decimal = Field(gt=0)
    source: str | None = "BCT"


class ValidateEntriesIn(In):
    ids: list[int]
