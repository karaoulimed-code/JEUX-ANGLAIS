"""Génération des écritures comptables PROPOSÉES.

Le logiciel tient le suivi auxiliaire des créances ; il ne remplace pas la
comptabilité générale. Chaque événement produit une écriture au statut
PROPOSEE, que le comptable valide puis exporte vers le logiciel comptable.
Les numéros de comptes sont paramétrables (paramètre « accounts »).
"""
import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..money import ZERO, q3
from ..models import (Adjustment, Allocation, Customer, Invoice, JournalEntry, JournalLine, Payment,
                      ProvisionCampaign, User, now_utc)
from .params import account, get_param
from .sequences import next_number


def _entry(db: Session, journal: str, date: dt.date, label: str, source_type: str, source_id: int,
           customer: Customer | None, lines: list[tuple[str, str | None, str, Decimal, Decimal]]) -> JournalEntry | None:
    lines = [ln for ln in lines if q3(ln[3]) != ZERO or q3(ln[4]) != ZERO]
    if not lines:
        return None
    debit = sum(q3(ln[3]) for ln in lines)
    credit = sum(q3(ln[4]) for ln in lines)
    if debit != credit:
        raise HTTPException(500, f"Écriture déséquilibrée ({label}) : débit {debit} ≠ crédit {credit}")
    e = JournalEntry(number=next_number(db, "ENTRY", date.year), journal=journal, entry_date=date, label=label[:250],
                     source_type=source_type, source_id=source_id, customer_id=customer.id if customer else None)
    for acc, aux, lab, d, c in lines:
        d, c = q3(d), q3(c)
        # une ligne négative est retournée de l'autre côté
        if d < 0:
            d, c = ZERO, c - d
        if c < 0:
            d, c = d - c, ZERO
        e.lines.append(JournalLine(account=acc, aux_account=aux, label=lab[:250], debit=d, credit=c))
    db.add(e)
    return e


def receivable_account(db: Session, inv: Invoice) -> str:
    if inv.classification in ("DOUTEUSE", "LITIGIEUSE"):
        return account(db, "clients_douteux")
    return account(db, "clients")


def on_invoice_validated(db: Session, inv: Invoice) -> None:
    if inv.source == "IMPORT" and not get_param(db, "import.generate_entries"):
        return
    cust = inv.customer
    rate = inv.exchange_rate
    lines = []
    tax_total_tnd = ZERO
    tax_lines = []
    for t in inv.taxes:
        amt = q3(t.amount * rate)
        tax_total_tnd += amt
        acc = t.account_code or account(db, "tva_collectee" if t.kind == "TVA" else ("timbre" if t.kind == "TIMBRE" else "autres_taxes"))
        tax_lines.append((acc, None, f"{t.label} {inv.number}", amt))
    sales = inv.total_ttc_tnd - tax_total_tnd  # le HT absorbe l'écart d'arrondi de conversion
    sign_fact = inv.doc_type == "FACTURE"
    acc_cli = account(db, "clients")
    label = f"{'Facture' if sign_fact else 'Avoir'} {inv.number} - {cust.legal_name}"
    if sign_fact:
        lines.append((acc_cli, cust.code, label, inv.total_ttc_tnd, ZERO))
        lines.append((account(db, "ventes"), None, label, ZERO, sales))
        lines += [(a, x, lab, ZERO, amt) for a, x, lab, amt in tax_lines]
    else:
        lines.append((acc_cli, cust.code, label, ZERO, inv.total_ttc_tnd))
        lines.append((account(db, "ventes"), None, label, sales, ZERO))
        lines += [(a, x, lab, amt, ZERO) for a, x, lab, amt in tax_lines]
    _entry(db, "VT", inv.issue_date, label, "INVOICE", inv.id, cust, lines)


def _payment_debit_account(db: Session, p: Payment) -> str:
    return {
        "ESPECES": account(db, "caisse"),
        "VIREMENT": account(db, "banque"),
        "CHEQUE": account(db, "cheques_a_encaisser"),
        "EFFET": account(db, "clients_effets"),
        "RETENUE_SOURCE": account(db, "retenue_source"),
    }.get(p.method_kind, p.method.account_code or account(db, "banque"))


def on_payment_created(db: Session, p: Payment) -> None:
    cust = p.customer
    acc = p.method.account_code or _payment_debit_account(db, p)
    label = f"Règlement {p.number} {p.method.label} {p.reference or ''} - {cust.legal_name}"
    _entry(db, "ENC", p.receipt_date, label, "PAYMENT", p.id, cust,
           [(acc, None, label, p.amount_tnd, ZERO), (account(db, "clients"), cust.code, label, ZERO, p.amount_tnd)])


def on_payment_status(db: Session, p: Payment, new_status: str, date: dt.date) -> None:
    cust = p.customer
    a_cli = account(db, "clients")
    holding = p.method.account_code or _payment_debit_account(db, p)
    bank = account(db, "banque")
    if new_status == "REMIS" and p.method_kind == "EFFET":
        label = f"Remise effet {p.reference or p.number} à l'encaissement"
        _entry(db, "ENC", date, label, "PAYMENT_STATUS", p.id, cust,
               [(account(db, "effets_a_encaisser"), None, label, p.amount_tnd, ZERO), (holding, None, label, ZERO, p.amount_tnd)])
    elif new_status == "ENCAISSE" and p.method_kind in ("CHEQUE", "EFFET"):
        src = account(db, "effets_a_encaisser") if (p.method_kind == "EFFET" and p.deposited_date) else holding
        label = f"Encaissement {p.method.label} {p.reference or p.number}"
        _entry(db, "ENC", date, label, "PAYMENT_STATUS", p.id, cust,
               [(bank, None, label, p.amount_tnd, ZERO), (src, None, label, ZERO, p.amount_tnd)])
    elif new_status in ("REJETE", "ANNULE"):
        if p.cleared_date or p.method_kind in ("VIREMENT",):
            src = bank
        elif p.method_kind == "EFFET" and p.deposited_date:
            src = account(db, "effets_a_encaisser")
        else:
            src = holding
        label = f"{'Rejet' if new_status == 'REJETE' else 'Annulation'} règlement {p.number} {p.reference or ''}"
        _entry(db, "ENC", date, label, "PAYMENT_STATUS", p.id, cust,
               [(a_cli, cust.code, label, p.amount_tnd, ZERO), (src, None, label, ZERO, p.amount_tnd)])


def on_allocation(db: Session, a: Allocation, reverse: bool = False) -> None:
    """Écart de change et transfert 416→411 pour la partie réglée d'une créance douteuse."""
    inv = a.invoice
    cust = inv.customer
    date = a.reversed_date if reverse else a.allocation_date
    sign = -1 if reverse else 1
    lines = []
    fx = a.fx_difference_tnd * sign
    a_cli = account(db, "clients")
    if fx != ZERO:
        label = f"Différence de change {inv.number}"
        if fx > 0:
            lines += [(a_cli, cust.code, label, fx, ZERO), (account(db, "gain_change"), None, label, ZERO, fx)]
        else:
            lines += [(account(db, "perte_change"), None, label, -fx, ZERO), (a_cli, cust.code, label, ZERO, -fx)]
    if inv.classification in ("DOUTEUSE", "LITIGIEUSE") and a.adjustment_id is None:
        label = f"Reclassement règlement créance douteuse {inv.number}"
        amt = a.amount_tnd * sign
        lines += [(a_cli, cust.code, label, amt, ZERO), (account(db, "clients_douteux"), cust.code, label, ZERO, amt)]
    if lines:
        _entry(db, "OD", date, f"Lettrage {inv.number}", "ALLOCATION", a.id, cust, lines)


def on_classification(db: Session, inv: Invoice, old: str, new: str, date: dt.date) -> None:
    doubtful = {"DOUTEUSE", "LITIGIEUSE"}
    if (old in doubtful) == (new in doubtful) or inv.balance <= 0:
        return
    cust = inv.customer
    amt = q3(inv.balance * inv.exchange_rate)
    a411, a416 = account(db, "clients"), account(db, "clients_douteux")
    label = f"Reclassement {inv.number} {old} → {new}"
    if new in doubtful:
        lines = [(a416, cust.code, label, amt, ZERO), (a411, cust.code, label, ZERO, amt)]
    else:
        lines = [(a411, cust.code, label, amt, ZERO), (a416, cust.code, label, ZERO, amt)]
    _entry(db, "OD", date, label, "CLASSIFICATION", inv.id, cust, lines)


def on_adjustment(db: Session, adj: Adjustment, inv: Invoice, provision_reversal_tnd: Decimal = ZERO) -> None:
    cust = db.get(Customer, adj.customer_id)
    acc_cli = receivable_account(db, inv) if adj.kind != "ECART_REGLEMENT" else account(db, "clients")
    label = f"{adj.kind.replace('_', ' ').capitalize()} {adj.number} {inv.number}"
    lines = []
    if adj.kind == "ECART_REGLEMENT":
        lines = [(account(db, "ecart_reglement_charge"), None, label, adj.amount_tnd, ZERO), (acc_cli, cust.code, label, ZERO, adj.amount_tnd)]
    else:
        vat_part = ZERO
        if get_param(db, "writeoff.recover_vat") and inv.total_ttc:
            vat_part = q3(adj.amount_tnd * inv.total_vat / inv.total_ttc)
        lines = [(account(db, "pertes_creances"), None, label, adj.amount_tnd - vat_part, ZERO)]
        if vat_part:
            lines.append((account(db, "tva_collectee"), None, label + " (régularisation TVA)", vat_part, ZERO))
        lines.append((acc_cli, cust.code, label, ZERO, adj.amount_tnd))
        if provision_reversal_tnd > 0:
            lines += [(account(db, "provision_clients"), None, "Reprise provision " + inv.number, provision_reversal_tnd, ZERO),
                      (account(db, "reprise_provisions"), None, "Reprise provision " + inv.number, ZERO, provision_reversal_tnd)]
    _entry(db, "OD", adj.date, label, "ADJUSTMENT", adj.id, cust, lines)


def on_provision_campaign(db: Session, c: ProvisionCampaign) -> None:
    dot = sum((ln.movement_tnd for ln in c.lines if ln.movement_tnd > 0), ZERO)
    rep = sum((-ln.movement_tnd for ln in c.lines if ln.movement_tnd < 0), ZERO)
    label = f"Provisions créances clients au {c.as_of:%d/%m/%Y} ({c.method})"
    lines = []
    if dot:
        lines += [(account(db, "dotation_provisions"), None, "Dotation " + label, dot, ZERO),
                  (account(db, "provision_clients"), None, "Dotation " + label, ZERO, dot)]
    if rep:
        lines += [(account(db, "provision_clients"), None, "Reprise " + label, rep, ZERO),
                  (account(db, "reprise_provisions"), None, "Reprise " + label, ZERO, rep)]
    _entry(db, "OD", c.as_of, label, "PROVISION", c.id, None, lines)


def validate_entry(db: Session, e: JournalEntry, user: User) -> None:
    if e.status != "PROPOSEE":
        raise HTTPException(409, "Seule une écriture proposée peut être validée")
    d = sum(ln.debit for ln in e.lines)
    c = sum(ln.credit for ln in e.lines)
    if d != c:
        raise HTTPException(409, "Écriture déséquilibrée")
    e.status = "VALIDEE"
    e.validated_by = user.id
    e.validated_at = now_utc()
