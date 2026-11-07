-- Script de création de la base « Gestion du poste clients » (PostgreSQL 14+)
-- Généré par : alembic upgrade head --sql — ne pas modifier à la main
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE audit_log (
    id BIGSERIAL NOT NULL, 
    ts TIMESTAMP WITH TIME ZONE NOT NULL, 
    user_id INTEGER, 
    username VARCHAR(60), 
    action VARCHAR(60) NOT NULL, 
    entity_type VARCHAR(40) NOT NULL, 
    entity_id VARCHAR(40), 
    details JSON, 
    ip VARCHAR(64), 
    prev_hash VARCHAR(64), 
    hash VARCHAR(64) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_audit_log_action ON audit_log (action);

CREATE INDEX ix_audit_log_entity_id ON audit_log (entity_id);

CREATE INDEX ix_audit_log_entity_type ON audit_log (entity_type);

CREATE INDEX ix_audit_log_ts ON audit_log (ts);

CREATE TABLE currencies (
    code VARCHAR(3) NOT NULL, 
    label VARCHAR(60) NOT NULL, 
    decimals INTEGER NOT NULL, 
    active BOOLEAN NOT NULL, 
    PRIMARY KEY (code)
);

CREATE TABLE dunning_templates (
    id SERIAL NOT NULL, 
    code VARCHAR(40) NOT NULL, 
    label VARCHAR(120) NOT NULL, 
    channel VARCHAR(20) NOT NULL, 
    subject VARCHAR(200), 
    body TEXT NOT NULL, 
    active BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (code)
);

CREATE TABLE payment_methods (
    id SERIAL NOT NULL, 
    code VARCHAR(30) NOT NULL, 
    label VARCHAR(120) NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    requires_clearing BOOLEAN NOT NULL, 
    account_code VARCHAR(20), 
    active BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (code)
);

CREATE TABLE reference_values (
    id SERIAL NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    code VARCHAR(40) NOT NULL, 
    label VARCHAR(120) NOT NULL, 
    active BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (kind, code)
);

CREATE TABLE sequences (
    id SERIAL NOT NULL, 
    key VARCHAR(20) NOT NULL, 
    year INTEGER NOT NULL, 
    next_value INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (key, year)
);

CREATE TABLE tax_rates (
    id SERIAL NOT NULL, 
    code VARCHAR(30) NOT NULL, 
    label VARCHAR(120) NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    rate NUMERIC(9, 4), 
    fixed_amount NUMERIC(18, 3), 
    account_code VARCHAR(20), 
    in_vat_base BOOLEAN NOT NULL, 
    valid_from DATE NOT NULL, 
    valid_to DATE, 
    active BOOLEAN NOT NULL, 
    source TEXT, 
    to_validate BOOLEAN NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_tax_rates_code ON tax_rates (code);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    username VARCHAR(60) NOT NULL, 
    full_name VARCHAR(150) NOT NULL, 
    email VARCHAR(150), 
    password_hash VARCHAR(200) NOT NULL, 
    role VARCHAR(30) NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    failed_attempts INTEGER NOT NULL, 
    locked_until TIMESTAMP WITH TIME ZONE, 
    must_change_password BOOLEAN NOT NULL, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE approval_requests (
    id SERIAL NOT NULL, 
    kind VARCHAR(30) NOT NULL, 
    entity_type VARCHAR(30) NOT NULL, 
    entity_id INTEGER NOT NULL, 
    payload JSON NOT NULL, 
    reason TEXT NOT NULL, 
    status VARCHAR(15) NOT NULL, 
    requested_by INTEGER NOT NULL, 
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    decided_by INTEGER, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    decision_comment TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(decided_by) REFERENCES users (id), 
    FOREIGN KEY(requested_by) REFERENCES users (id)
);

CREATE TABLE attachments (
    id SERIAL NOT NULL, 
    entity_type VARCHAR(30) NOT NULL, 
    entity_id INTEGER NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    content_type VARCHAR(120), 
    size INTEGER NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    storage_path VARCHAR(400) NOT NULL, 
    description VARCHAR(255), 
    uploaded_by INTEGER, 
    uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(uploaded_by) REFERENCES users (id)
);

CREATE INDEX ix_attachments_entity_id ON attachments (entity_id);

CREATE INDEX ix_attachments_entity_type ON attachments (entity_type);

CREATE TABLE customers (
    id SERIAL NOT NULL, 
    code VARCHAR(30) NOT NULL, 
    legal_name VARCHAR(200) NOT NULL, 
    trade_name VARCHAR(200), 
    tax_id VARCHAR(40), 
    rne_id VARCHAR(40), 
    address TEXT, 
    city VARCHAR(80), 
    postal_code VARCHAR(10), 
    country VARCHAR(2) NOT NULL, 
    phone VARCHAR(40), 
    email VARCHAR(150), 
    activity VARCHAR(200), 
    category_code VARCHAR(40), 
    sector_code VARCHAR(40), 
    zone_code VARCHAR(40), 
    group_code VARCHAR(40), 
    salesperson_id INTEGER, 
    contact_name VARCHAR(150), 
    contact_function VARCHAR(100), 
    contact_phone VARCHAR(40), 
    contact_email VARCHAR(150), 
    bank_name VARCHAR(100), 
    bank_rib VARCHAR(40), 
    payment_terms_days INTEGER NOT NULL, 
    payment_terms_label VARCHAR(120), 
    currency VARCHAR(3) NOT NULL, 
    credit_limit NUMERIC(18, 3) NOT NULL, 
    max_exposure NUMERIC(18, 3) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    in_litigation BOOLEAN NOT NULL, 
    risk_score INTEGER, 
    risk_class VARCHAR(20), 
    risk_computed_at TIMESTAMP WITH TIME ZONE, 
    notes TEXT, 
    is_demo BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(salesperson_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_customers_code ON customers (code);

CREATE INDEX ix_customers_legal_name ON customers (legal_name);

CREATE INDEX ix_customers_tax_id ON customers (tax_id);

CREATE TABLE dunning_levels (
    id SERIAL NOT NULL, 
    level INTEGER NOT NULL, 
    code VARCHAR(40) NOT NULL, 
    label VARCHAR(120) NOT NULL, 
    days_after_due INTEGER NOT NULL, 
    min_amount NUMERIC(18, 3) NOT NULL, 
    template_id INTEGER, 
    escalate_to_legal BOOLEAN NOT NULL, 
    active BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(template_id) REFERENCES dunning_templates (id), 
    UNIQUE (level)
);

CREATE TABLE exchange_rates (
    id SERIAL NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    date DATE NOT NULL, 
    rate NUMERIC(18, 6) NOT NULL, 
    source VARCHAR(60), 
    PRIMARY KEY (id), 
    FOREIGN KEY(currency) REFERENCES currencies (code), 
    UNIQUE (currency, date)
);

CREATE TABLE parameters (
    id SERIAL NOT NULL, 
    key VARCHAR(80) NOT NULL, 
    value JSON, 
    valid_from DATE NOT NULL, 
    description TEXT, 
    source TEXT, 
    to_validate BOOLEAN NOT NULL, 
    updated_by INTEGER, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(updated_by) REFERENCES users (id), 
    UNIQUE (key, valid_from)
);

CREATE INDEX ix_parameters_key ON parameters (key);

CREATE TABLE provision_campaigns (
    id SERIAL NOT NULL, 
    as_of DATE NOT NULL, 
    method VARCHAR(10) NOT NULL, 
    status VARCHAR(15) NOT NULL, 
    notes TEXT, 
    total_amount_tnd NUMERIC(18, 3) NOT NULL, 
    created_by INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    validated_by INTEGER, 
    validated_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id), 
    FOREIGN KEY(validated_by) REFERENCES users (id)
);

CREATE TABLE user_sessions (
    id VARCHAR(64) NOT NULL, 
    user_id INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    ip VARCHAR(64), 
    user_agent VARCHAR(300), 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_user_sessions_user_id ON user_sessions (user_id);

CREATE TABLE adjustments (
    id SERIAL NOT NULL, 
    number VARCHAR(40) NOT NULL, 
    customer_id INTEGER NOT NULL, 
    kind VARCHAR(25) NOT NULL, 
    date DATE NOT NULL, 
    amount NUMERIC(18, 3) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    exchange_rate NUMERIC(18, 6) NOT NULL, 
    amount_tnd NUMERIC(18, 3) NOT NULL, 
    allocated_amount NUMERIC(18, 3) NOT NULL, 
    reason TEXT NOT NULL, 
    approval_id INTEGER, 
    created_by INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (amount > 0), 
    FOREIGN KEY(approval_id) REFERENCES approval_requests (id), 
    FOREIGN KEY(created_by) REFERENCES users (id), 
    FOREIGN KEY(customer_id) REFERENCES customers (id), 
    UNIQUE (number)
);

CREATE INDEX ix_adjustments_customer_id ON adjustments (customer_id);

CREATE TABLE dunning_actions (
    id SERIAL NOT NULL, 
    customer_id INTEGER NOT NULL, 
    level_id INTEGER, 
    action_type VARCHAR(30) NOT NULL, 
    action_date DATE NOT NULL, 
    channel VARCHAR(20) NOT NULL, 
    responsible_id INTEGER, 
    result_code VARCHAR(30), 
    result TEXT, 
    promised_date DATE, 
    promised_amount NUMERIC(18, 3), 
    next_action VARCHAR(200), 
    next_action_date DATE, 
    comments TEXT, 
    amount_due_tnd NUMERIC(18, 3) NOT NULL, 
    rendered_subject VARCHAR(250), 
    rendered_text TEXT, 
    created_by INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id), 
    FOREIGN KEY(customer_id) REFERENCES customers (id), 
    FOREIGN KEY(level_id) REFERENCES dunning_levels (id), 
    FOREIGN KEY(responsible_id) REFERENCES users (id)
);

CREATE INDEX ix_dunning_actions_action_date ON dunning_actions (action_date);

CREATE INDEX ix_dunning_actions_customer_id ON dunning_actions (customer_id);

CREATE INDEX ix_dunning_actions_next_action_date ON dunning_actions (next_action_date);

CREATE TABLE invoices (
    id SERIAL NOT NULL, 
    doc_type VARCHAR(10) NOT NULL, 
    number VARCHAR(40), 
    external_ref VARCHAR(60), 
    source VARCHAR(20) NOT NULL, 
    customer_id INTEGER NOT NULL, 
    issue_date DATE NOT NULL, 
    due_date DATE NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    exchange_rate NUMERIC(18, 6) NOT NULL, 
    total_ht NUMERIC(18, 3) NOT NULL, 
    total_vat NUMERIC(18, 3) NOT NULL, 
    total_other_taxes NUMERIC(18, 3) NOT NULL, 
    total_ttc NUMERIC(18, 3) NOT NULL, 
    total_ttc_tnd NUMERIC(18, 3) NOT NULL, 
    total_ht_tnd NUMERIC(18, 3) NOT NULL, 
    paid_amount NUMERIC(18, 3) NOT NULL, 
    balance NUMERIC(18, 3) NOT NULL, 
    lifecycle VARCHAR(12) NOT NULL, 
    classification VARCHAR(15) NOT NULL, 
    classification_reason TEXT, 
    classified_at TIMESTAMP WITH TIME ZONE, 
    related_invoice_id INTEGER, 
    salesperson_id INTEGER, 
    order_ref VARCHAR(60), 
    notes TEXT, 
    created_by INTEGER, 
    validated_by INTEGER, 
    validated_at TIMESTAMP WITH TIME ZONE, 
    is_demo BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (classification in ('NORMALE','LITIGIEUSE','DOUTEUSE','IRRECOUVRABLE')), 
    CHECK (doc_type in ('FACTURE','AVOIR')), 
    CHECK (lifecycle in ('BROUILLON','VALIDEE')), 
    FOREIGN KEY(created_by) REFERENCES users (id), 
    FOREIGN KEY(customer_id) REFERENCES customers (id), 
    FOREIGN KEY(related_invoice_id) REFERENCES invoices (id), 
    FOREIGN KEY(salesperson_id) REFERENCES users (id), 
    FOREIGN KEY(validated_by) REFERENCES users (id), 
    CONSTRAINT uq_invoice_number UNIQUE (doc_type, number)
);

CREATE INDEX ix_invoices_customer_id ON invoices (customer_id);

CREATE INDEX ix_invoices_due_date ON invoices (due_date);

CREATE INDEX ix_invoices_external_ref ON invoices (external_ref);

CREATE INDEX ix_invoices_issue_date ON invoices (issue_date);

CREATE INDEX ix_invoices_number ON invoices (number);

CREATE TABLE journal_entries (
    id SERIAL NOT NULL, 
    number VARCHAR(40) NOT NULL, 
    journal VARCHAR(10) NOT NULL, 
    entry_date DATE NOT NULL, 
    label VARCHAR(250) NOT NULL, 
    source_type VARCHAR(30) NOT NULL, 
    source_id INTEGER NOT NULL, 
    customer_id INTEGER, 
    status VARCHAR(10) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    validated_by INTEGER, 
    validated_at TIMESTAMP WITH TIME ZONE, 
    export_batch VARCHAR(40), 
    exported_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CHECK (status in ('PROPOSEE','VALIDEE','EXPORTEE','REJETEE')), 
    FOREIGN KEY(customer_id) REFERENCES customers (id), 
    FOREIGN KEY(validated_by) REFERENCES users (id), 
    UNIQUE (number)
);

CREATE INDEX ix_journal_entries_entry_date ON journal_entries (entry_date);

CREATE TABLE payments (
    id SERIAL NOT NULL, 
    number VARCHAR(40) NOT NULL, 
    customer_id INTEGER NOT NULL, 
    method_id INTEGER NOT NULL, 
    method_kind VARCHAR(20) NOT NULL, 
    receipt_date DATE NOT NULL, 
    value_date DATE, 
    amount NUMERIC(18, 3) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    exchange_rate NUMERIC(18, 6) NOT NULL, 
    amount_tnd NUMERIC(18, 3) NOT NULL, 
    allocated_amount NUMERIC(18, 3) NOT NULL, 
    reference VARCHAR(80), 
    bank_name VARCHAR(100), 
    drawer VARCHAR(150), 
    status VARCHAR(20) NOT NULL, 
    deposited_date DATE, 
    cleared_date DATE, 
    rejected_date DATE, 
    rejection_reason VARCHAR(255), 
    cancelled_date DATE, 
    cancel_reason VARCHAR(255), 
    notes TEXT, 
    created_by INTEGER, 
    is_demo BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status in ('EN_PORTEFEUILLE','REMIS','ENCAISSE','REJETE','ANNULE')), 
    CHECK (amount > 0), 
    FOREIGN KEY(created_by) REFERENCES users (id), 
    FOREIGN KEY(customer_id) REFERENCES customers (id), 
    FOREIGN KEY(method_id) REFERENCES payment_methods (id), 
    UNIQUE (number)
);

CREATE INDEX ix_payments_customer_id ON payments (customer_id);

CREATE INDEX ix_payments_receipt_date ON payments (receipt_date);

CREATE TABLE risk_snapshots (
    id SERIAL NOT NULL, 
    customer_id INTEGER NOT NULL, 
    as_of DATE NOT NULL, 
    computed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    score INTEGER NOT NULL, 
    risk_class VARCHAR(20) NOT NULL, 
    details JSON NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE INDEX ix_risk_snapshots_customer_id ON risk_snapshots (customer_id);

CREATE TABLE dunning_action_invoices (
    id SERIAL NOT NULL, 
    action_id INTEGER NOT NULL, 
    invoice_id INTEGER NOT NULL, 
    balance_at_action NUMERIC(18, 3) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(action_id) REFERENCES dunning_actions (id) ON DELETE CASCADE, 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id)
);

CREATE INDEX ix_dunning_action_invoices_action_id ON dunning_action_invoices (action_id);

CREATE INDEX ix_dunning_action_invoices_invoice_id ON dunning_action_invoices (invoice_id);

CREATE TABLE installments (
    id SERIAL NOT NULL, 
    invoice_id INTEGER NOT NULL, 
    seq INTEGER NOT NULL, 
    due_date DATE NOT NULL, 
    amount NUMERIC(18, 3) NOT NULL, 
    amount_tnd NUMERIC(18, 3) NOT NULL, 
    paid_amount NUMERIC(18, 3) NOT NULL, 
    paid_amount_tnd NUMERIC(18, 3) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE, 
    UNIQUE (invoice_id, seq)
);

CREATE INDEX ix_installments_due_date ON installments (due_date);

CREATE INDEX ix_installments_invoice_id ON installments (invoice_id);

CREATE TABLE invoice_lines (
    id SERIAL NOT NULL, 
    invoice_id INTEGER NOT NULL, 
    position INTEGER NOT NULL, 
    description VARCHAR(300) NOT NULL, 
    quantity NUMERIC(18, 3) NOT NULL, 
    unit_price NUMERIC(18, 3) NOT NULL, 
    discount_pct NUMERIC(7, 3) NOT NULL, 
    vat_code VARCHAR(30), 
    vat_rate NUMERIC(9, 4) NOT NULL, 
    amount_ht NUMERIC(18, 3) NOT NULL, 
    vat_amount NUMERIC(18, 3) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
);

CREATE INDEX ix_invoice_lines_invoice_id ON invoice_lines (invoice_id);

CREATE TABLE invoice_taxes (
    id SERIAL NOT NULL, 
    invoice_id INTEGER NOT NULL, 
    code VARCHAR(30) NOT NULL, 
    label VARCHAR(120) NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    base NUMERIC(18, 3) NOT NULL, 
    rate NUMERIC(9, 4), 
    amount NUMERIC(18, 3) NOT NULL, 
    account_code VARCHAR(20), 
    PRIMARY KEY (id), 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
);

CREATE INDEX ix_invoice_taxes_invoice_id ON invoice_taxes (invoice_id);

CREATE TABLE journal_lines (
    id SERIAL NOT NULL, 
    entry_id INTEGER NOT NULL, 
    account VARCHAR(20) NOT NULL, 
    aux_account VARCHAR(30), 
    label VARCHAR(250) NOT NULL, 
    debit NUMERIC(18, 3) NOT NULL, 
    credit NUMERIC(18, 3) NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (debit >= 0 AND credit >= 0), 
    FOREIGN KEY(entry_id) REFERENCES journal_entries (id) ON DELETE CASCADE
);

CREATE INDEX ix_journal_lines_entry_id ON journal_lines (entry_id);

CREATE TABLE provisions (
    id SERIAL NOT NULL, 
    campaign_id INTEGER NOT NULL, 
    invoice_id INTEGER NOT NULL, 
    customer_id INTEGER NOT NULL, 
    method VARCHAR(10) NOT NULL, 
    bucket VARCHAR(20), 
    days_overdue INTEGER NOT NULL, 
    outstanding_tnd NUMERIC(18, 3) NOT NULL, 
    base_tnd NUMERIC(18, 3) NOT NULL, 
    rate NUMERIC(9, 4) NOT NULL, 
    suggested_rate NUMERIC(9, 4) NOT NULL, 
    amount_tnd NUMERIC(18, 3) NOT NULL, 
    previous_amount_tnd NUMERIC(18, 3) NOT NULL, 
    movement_tnd NUMERIC(18, 3) NOT NULL, 
    justification TEXT, 
    fiscal_deductible BOOLEAN NOT NULL, 
    fiscal_note TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(campaign_id) REFERENCES provision_campaigns (id) ON DELETE CASCADE, 
    FOREIGN KEY(customer_id) REFERENCES customers (id), 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id)
);

CREATE INDEX ix_provisions_campaign_id ON provisions (campaign_id);

CREATE INDEX ix_provisions_customer_id ON provisions (customer_id);

CREATE INDEX ix_provisions_invoice_id ON provisions (invoice_id);

CREATE TABLE allocations (
    id SERIAL NOT NULL, 
    customer_id INTEGER NOT NULL, 
    invoice_id INTEGER NOT NULL, 
    installment_id INTEGER NOT NULL, 
    payment_id INTEGER, 
    credit_note_id INTEGER, 
    adjustment_id INTEGER, 
    amount NUMERIC(18, 3) NOT NULL, 
    amount_tnd NUMERIC(18, 3) NOT NULL, 
    source_amount_tnd NUMERIC(18, 3) NOT NULL, 
    fx_difference_tnd NUMERIC(18, 3) NOT NULL, 
    allocation_date DATE NOT NULL, 
    created_by INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    reversed_at TIMESTAMP WITH TIME ZONE, 
    reversed_date DATE, 
    reversed_by INTEGER, 
    reversal_reason VARCHAR(255), 
    PRIMARY KEY (id), 
    CONSTRAINT ck_allocation_one_source CHECK ((CASE WHEN payment_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN credit_note_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN adjustment_id IS NOT NULL THEN 1 ELSE 0 END) = 1), 
    CHECK (amount > 0), 
    FOREIGN KEY(adjustment_id) REFERENCES adjustments (id), 
    FOREIGN KEY(created_by) REFERENCES users (id), 
    FOREIGN KEY(credit_note_id) REFERENCES invoices (id), 
    FOREIGN KEY(customer_id) REFERENCES customers (id), 
    FOREIGN KEY(installment_id) REFERENCES installments (id), 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id), 
    FOREIGN KEY(payment_id) REFERENCES payments (id), 
    FOREIGN KEY(reversed_by) REFERENCES users (id)
);

CREATE INDEX ix_alloc_active ON allocations (installment_id, reversed_at);

CREATE INDEX ix_allocations_adjustment_id ON allocations (adjustment_id);

CREATE INDEX ix_allocations_allocation_date ON allocations (allocation_date);

CREATE INDEX ix_allocations_credit_note_id ON allocations (credit_note_id);

CREATE INDEX ix_allocations_customer_id ON allocations (customer_id);

CREATE INDEX ix_allocations_installment_id ON allocations (installment_id);

CREATE INDEX ix_allocations_invoice_id ON allocations (invoice_id);

CREATE INDEX ix_allocations_payment_id ON allocations (payment_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

CREATE OR REPLACE FUNCTION gpc_forbid() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'INTERDIT : %%', TG_ARGV[0];
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_immutable BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION gpc_forbid('le journal d''audit est inaltérable');

CREATE OR REPLACE FUNCTION gpc_invoice_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.lifecycle = 'VALIDEE' THEN
      RAISE EXCEPTION 'INTERDIT : une pièce validée ne peut pas être supprimée, émettez un avoir';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.lifecycle = 'VALIDEE' AND (
       NEW.lifecycle <> OLD.lifecycle OR NEW.doc_type <> OLD.doc_type OR NEW.number IS DISTINCT FROM OLD.number
    OR NEW.customer_id <> OLD.customer_id OR NEW.issue_date <> OLD.issue_date OR NEW.currency <> OLD.currency
    OR NEW.exchange_rate <> OLD.exchange_rate OR NEW.total_ht <> OLD.total_ht OR NEW.total_vat <> OLD.total_vat
    OR NEW.total_other_taxes <> OLD.total_other_taxes OR NEW.total_ttc <> OLD.total_ttc OR NEW.total_ttc_tnd <> OLD.total_ttc_tnd) THEN
    RAISE EXCEPTION 'INTERDIT : les données d''une pièce validée sont intangibles, émettez un avoir';
  END IF;
  IF NEW.paid_amount < 0 OR NEW.paid_amount > NEW.total_ttc OR NEW.balance <> NEW.total_ttc - NEW.paid_amount THEN
    RAISE EXCEPTION 'INTERDIT : incohérence entre montant réglé et solde de la pièce %%', NEW.number;
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER invoices_guard BEFORE UPDATE OR DELETE ON invoices FOR EACH ROW EXECUTE FUNCTION gpc_invoice_guard();

CREATE OR REPLACE FUNCTION gpc_child_guard() RETURNS trigger AS $$
DECLARE inv_id integer; st text; vat timestamptz;
BEGIN
  inv_id := COALESCE(NEW.invoice_id, OLD.invoice_id);
  SELECT lifecycle, validated_at INTO st, vat FROM invoices WHERE id = inv_id;
  IF st = 'VALIDEE' AND vat < transaction_timestamp() THEN
    IF TG_TABLE_NAME = 'installments' AND TG_OP = 'UPDATE'
       AND NEW.due_date = OLD.due_date AND NEW.amount = OLD.amount AND NEW.amount_tnd = OLD.amount_tnd THEN
      IF NEW.paid_amount < 0 OR NEW.paid_amount > NEW.amount THEN
        RAISE EXCEPTION 'INTERDIT : montant réglé incohérent sur une échéance';
      END IF;
      RETURN NEW;  -- seule la mise à jour du montant réglé est permise
    END IF;
    RAISE EXCEPTION 'INTERDIT : le détail d''une pièce validée est intangible';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER invoice_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON invoice_lines FOR EACH ROW EXECUTE FUNCTION gpc_child_guard();
CREATE TRIGGER invoice_taxes_guard BEFORE INSERT OR UPDATE OR DELETE ON invoice_taxes FOR EACH ROW EXECUTE FUNCTION gpc_child_guard();
CREATE TRIGGER installments_guard BEFORE INSERT OR UPDATE OR DELETE ON installments FOR EACH ROW EXECUTE FUNCTION gpc_child_guard();

CREATE TRIGGER payments_no_delete BEFORE DELETE ON payments FOR EACH ROW EXECUTE FUNCTION gpc_forbid('un règlement ne se supprime pas, il s''annule par contre-passation');
CREATE TRIGGER allocations_no_delete BEFORE DELETE ON allocations FOR EACH ROW EXECUTE FUNCTION gpc_forbid('une affectation ne se supprime pas, elle s''annule');
CREATE TRIGGER adjustments_no_change BEFORE UPDATE OF amount, amount_tnd, customer_id, date OR DELETE ON adjustments FOR EACH ROW EXECUTE FUNCTION gpc_forbid('une OD validée est intangible');

CREATE OR REPLACE FUNCTION gpc_payment_guard() RETURNS trigger AS $$
BEGIN
  IF NEW.amount <> OLD.amount OR NEW.amount_tnd <> OLD.amount_tnd OR NEW.customer_id <> OLD.customer_id
     OR NEW.receipt_date <> OLD.receipt_date OR NEW.currency <> OLD.currency OR NEW.exchange_rate <> OLD.exchange_rate THEN
    RAISE EXCEPTION 'INTERDIT : les données d''un règlement enregistré sont intangibles';
  END IF;
  IF OLD.status IN ('REJETE','ANNULE') AND NEW.status <> OLD.status THEN
    RAISE EXCEPTION 'INTERDIT : un règlement rejeté ou annulé ne peut plus changer de statut';
  END IF;
  IF NEW.allocated_amount < 0 OR NEW.allocated_amount > NEW.amount THEN
    RAISE EXCEPTION 'INTERDIT : affectation supérieure au montant du règlement';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER payments_guard BEFORE UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION gpc_payment_guard();

CREATE OR REPLACE FUNCTION gpc_alloc_guard() RETURNS trigger AS $$
BEGIN
  IF NEW.amount <> OLD.amount OR NEW.installment_id <> OLD.installment_id OR NEW.payment_id IS DISTINCT FROM OLD.payment_id
     OR NEW.credit_note_id IS DISTINCT FROM OLD.credit_note_id OR NEW.adjustment_id IS DISTINCT FROM OLD.adjustment_id
     OR NEW.allocation_date <> OLD.allocation_date OR (OLD.reversed_at IS NOT NULL) THEN
    RAISE EXCEPTION 'INTERDIT : une affectation ne peut être que contre-passée, une seule fois';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER allocations_guard BEFORE UPDATE ON allocations FOR EACH ROW EXECUTE FUNCTION gpc_alloc_guard();

CREATE OR REPLACE FUNCTION gpc_entry_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'PROPOSEE' THEN RAISE EXCEPTION 'INTERDIT : écriture validée ou exportée'; END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'EXPORTEE' THEN
    RAISE EXCEPTION 'INTERDIT : une écriture exportée est intangible';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER journal_entries_guard BEFORE UPDATE OR DELETE ON journal_entries FOR EACH ROW EXECUTE FUNCTION gpc_entry_guard();

CREATE OR REPLACE FUNCTION gpc_entry_line_guard() RETURNS trigger AS $$
DECLARE st text;
BEGIN
  SELECT status INTO st FROM journal_entries WHERE id = COALESCE(NEW.entry_id, OLD.entry_id);
  IF st IN ('VALIDEE','EXPORTEE') THEN RAISE EXCEPTION 'INTERDIT : lignes d''une écriture validée'; END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER journal_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON journal_lines FOR EACH ROW EXECUTE FUNCTION gpc_entry_line_guard();;

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

COMMIT;

