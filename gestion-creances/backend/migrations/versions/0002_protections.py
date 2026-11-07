"""Protections d'intégrité au niveau de la base (contrôle interne)

Même un accès direct à l'application ne permet pas :
- de modifier ou supprimer le journal d'audit ;
- de modifier les montants d'une facture validée ou de la supprimer ;
- de supprimer un règlement, une affectation ou une OD (contre-passation obligatoire) ;
- de modifier une écriture exportée.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL = r"""
CREATE OR REPLACE FUNCTION gpc_forbid() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'INTERDIT : %', TG_ARGV[0];
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
    RAISE EXCEPTION 'INTERDIT : incohérence entre montant réglé et solde de la pièce %', NEW.number;
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
CREATE TRIGGER journal_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON journal_lines FOR EACH ROW EXECUTE FUNCTION gpc_entry_line_guard();
"""

DOWN = """
DROP TRIGGER IF EXISTS audit_log_immutable ON audit_log;
DROP TRIGGER IF EXISTS invoices_guard ON invoices;
DROP TRIGGER IF EXISTS invoice_lines_guard ON invoice_lines;
DROP TRIGGER IF EXISTS invoice_taxes_guard ON invoice_taxes;
DROP TRIGGER IF EXISTS installments_guard ON installments;
DROP TRIGGER IF EXISTS payments_no_delete ON payments;
DROP TRIGGER IF EXISTS allocations_no_delete ON allocations;
DROP TRIGGER IF EXISTS adjustments_no_change ON adjustments;
DROP TRIGGER IF EXISTS payments_guard ON payments;
DROP TRIGGER IF EXISTS allocations_guard ON allocations;
DROP TRIGGER IF EXISTS journal_entries_guard ON journal_entries;
DROP TRIGGER IF EXISTS journal_lines_guard ON journal_lines;
DROP FUNCTION IF EXISTS gpc_forbid, gpc_invoice_guard, gpc_child_guard, gpc_payment_guard, gpc_alloc_guard, gpc_entry_guard, gpc_entry_line_guard;
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute(DOWN)
