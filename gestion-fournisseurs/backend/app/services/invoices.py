"""Modules 3, 4 et 7 — Factures, contrôles (rapprochement à 3 niveaux), validation, avoirs, acomptes."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from ..models import (Attachment, CreditAllocation, Dispute, GoodsReceipt, GoodsReceiptLine,
                      Invoice, InvoiceApproval, InvoiceLine, Payment, PaymentAllocation,
                      PurchaseOrder, PurchaseOrderLine, Supplier)
from ..money import D, ZERO, pct, r3
from ..permissions import INVOICE_LEVEL_ROLES, has_permission
from ..security import BusinessError, Ctx
from . import accounting
from .common import (account, check_period_open, ctx_audit, fx_rate, next_number, setting_bool,
                     setting_dec, tax_rate_by_code, tax_rates)

SETTLED_PAYMENT_STATUSES = ("emis", "debite")
ACTIVE_WF = ("en_attente_validation", "validee")


def normalize_number(n: str) -> str:
    """« FA-00123 », « fa 123 » et « FA123 » donnent la même clé (contrôle des doublons)."""
    tokens = re.findall(r"[A-Z]+|\d+", n.upper())
    return "".join(t.lstrip("0") or "0" if t.isdigit() else t for t in tokens) or "0"


def compute_due_date(inv_date: date, days: int, kind: str) -> date:
    d = inv_date + timedelta(days=days)
    if kind == "fin_de_mois":
        d = d.replace(day=calendar.monthrange(d.year, d.month)[1])
    return d


# ------------------------------------------------------------------ calculs de soldes
def settled_amount(db, inv: Invoice, as_of: date | None = None) -> Decimal:
    q = (select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
         .join(Payment, Payment.id == PaymentAllocation.payment_id)
         .where(PaymentAllocation.invoice_id == inv.id, PaymentAllocation.cancelled.is_(False),
                Payment.status.in_(SETTLED_PAYMENT_STATUSES)))
    q2 = select(func.coalesce(func.sum(CreditAllocation.amount), 0)).where(
        CreditAllocation.target_invoice_id == inv.id, CreditAllocation.cancelled.is_(False))
    if as_of:
        q = q.where(PaymentAllocation.allocation_date <= as_of)
        q2 = q2.where(CreditAllocation.allocation_date <= as_of)
    return r3(D(db.scalar(q)) + D(db.scalar(q2)))


def consumed_credit(db, inv: Invoice, as_of: date | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(CreditAllocation.amount), 0)).where(
        CreditAllocation.source_invoice_id == inv.id, CreditAllocation.cancelled.is_(False))
    if as_of:
        q = q.where(CreditAllocation.allocation_date <= as_of)
    return r3(D(db.scalar(q)))


def balance(db, inv: Invoice, as_of: date | None = None) -> Decimal:
    """Solde restant dû en devise de facture (négatif pour un avoir non imputé)."""
    if inv.workflow_status == "annulee" and (as_of is None or not inv.cancelled_at or inv.cancelled_at <= as_of):
        return ZERO
    if inv.doc_type == "avoir":
        return -r3(D(inv.total_ttc) - consumed_credit(db, inv, as_of))
    return r3(D(inv.total_ttc) - settled_amount(db, inv, as_of))


def disputed_amount(db, inv: Invoice) -> Decimal:
    v = db.scalar(select(func.coalesce(func.sum(Dispute.contested_amount), 0)).where(
        Dispute.invoice_id == inv.id, Dispute.status.in_(("ouvert", "en_cours"))))
    return r3(D(v))


def has_open_dispute(db, inv: Invoice) -> bool:
    return bool(db.scalar(select(func.count(Dispute.id)).where(
        Dispute.invoice_id == inv.id, Dispute.status.in_(("ouvert", "en_cours")))))


def display_status(db, inv: Invoice, today: date | None = None) -> str:
    today = today or date.today()
    if inv.workflow_status in ("brouillon", "en_attente_validation", "annulee"):
        return inv.workflow_status
    if has_open_dispute(db, inv):
        return "en_litige"
    bal = balance(db, inv)
    if inv.doc_type == "avoir":
        return "reglee" if bal == 0 else "validee"
    if bal <= 0:
        return "reglee"
    if bal < D(inv.total_ttc):
        return "partiellement_reglee"
    if inv.due_date and inv.due_date < today:
        return "echue"
    return "non_echue"


# ------------------------------------------------------------------ saisie
def _fill(ctx: Ctx, inv: Invoice, data: dict, lines: list[dict]) -> None:
    sup = ctx.db.get(Supplier, inv.supplier_id)
    if not sup or sup.company_id != ctx.company_id:
        raise BusinessError("Fournisseur introuvable.", status=404)
    if not lines:
        raise BusinessError("La facture doit comporter au moins une ligne.")
    inv.number_normalized = normalize_number(inv.supplier_number)
    inv.currency = data.get("currency") or sup.currency
    if inv.order_id:
        po = ctx.db.get(PurchaseOrder, inv.order_id)
        if not po or po.company_id != ctx.company_id:
            raise BusinessError("Bon de commande introuvable.", status=404)
    inv.exchange_rate = D(data["exchange_rate"]) if data.get("exchange_rate") else fx_rate(
        ctx.db, ctx.company_id, inv.currency, inv.invoice_date)
    default_acc = sup.default_account or account(ctx.db, ctx.company_id, "achats_defaut")
    if inv.doc_type == "acompte":
        default_acc = account(ctx.db, ctx.company_id, "avances_fournisseurs")
    inv.lines.clear()
    ht = tva = ZERO
    for l in lines:
        qty, pu = D(l["quantity"]), D(l["unit_price"])
        if qty <= 0 or pu < 0:
            raise BusinessError("Quantités strictement positives et prix unitaires positifs exigés "
                                "(un avoir se saisit en montants positifs).")
        acc = l.get("account_code")
        if not acc and l.get("order_line_id"):
            pol = ctx.db.get(PurchaseOrderLine, l["order_line_id"])
            acc = pol.account_code if pol else None
        base = r3(qty * pu)
        amount_ht = r3(D(l["amount_ht"])) if l.get("amount_ht") is not None else base
        amount_tva = r3(D(l["amount_tva"])) if l.get("amount_tva") is not None else pct(amount_ht, l.get("tva_rate", 19))
        inv.lines.append(InvoiceLine(
            order_line_id=l.get("order_line_id"), item_ref=l.get("item_ref"), description=l["description"],
            quantity=qty, unit_price=pu, tva_rate=D(l.get("tva_rate", 19)), amount_ht=amount_ht,
            amount_tva=amount_tva, account_code=acc or default_acc))
        ht += amount_ht
        tva += amount_tva
    inv.total_ht, inv.total_tva = r3(ht), r3(tva)
    if data.get("stamp_duty") is not None:
        inv.stamp_duty = r3(D(data["stamp_duty"]))
    elif inv.doc_type != "avoir" and sup.is_resident:
        st = tax_rates(ctx.db, ctx.company_id, "TIMBRE", inv.invoice_date)
        inv.stamp_duty = r3(st[0].fixed_amount) if st else ZERO
    else:
        inv.stamp_duty = ZERO
    inv.other_taxes = r3(D(data.get("other_taxes") or 0))
    inv.total_ttc = r3(inv.total_ht + inv.total_tva + D(inv.stamp_duty) + D(inv.other_taxes))
    inv.total_ttc_tnd = r3(D(inv.total_ttc) * D(inv.exchange_rate))
    # Retenue à la source (prévisionnelle ; opérée lors du paiement)
    inv.rs_code, inv.rs_rate, inv.rs_amount = None, ZERO, ZERO
    rs_code = data.get("rs_code") or sup.rs_code
    if rs_code == "AUCUNE":  # dispense explicite (ex. attestation d'exonération de retenue fournie)
        rs_code = None
    if inv.doc_type != "avoir" and rs_code:
        rate = tax_rate_by_code(ctx.db, ctx.company_id, rs_code, inv.invoice_date)
        if not rate:
            raise BusinessError(f"Taux de retenue à la source « {rs_code} » inconnu ou non en vigueur à la date de facture.")
        inv.rs_code = rs_code
        if inv.total_ttc_tnd >= D(rate.threshold):
            inv.rs_rate = D(rate.rate)
            inv.rs_amount = pct(inv.total_ttc, rate.rate)
    inv.net_to_pay = r3(D(inv.total_ttc) - D(inv.rs_amount))
    if data.get("due_date"):
        inv.due_date = data["due_date"]
    else:
        po = ctx.db.get(PurchaseOrder, inv.order_id) if inv.order_id else None
        days = po.payment_terms_days if po else sup.payment_terms_days
        kind = po.payment_terms_type if po else sup.payment_terms_type
        inv.due_date = compute_due_date(inv.invoice_date, days, kind)


def create_invoice(ctx: Ctx, data: dict) -> Invoice:
    data = dict(data)
    lines = data.pop("lines")
    if data.get("doc_type", "facture") not in ("facture", "avoir", "acompte"):
        raise BusinessError("Type de document inconnu.")
    inv = Invoice(company_id=ctx.company_id, created_by_id=ctx.user.id,
                  internal_ref=next_number(ctx.db, ctx.company_id,
                                           {"facture": "FA", "avoir": "AV", "acompte": "AC"}[data.get("doc_type", "facture")],
                                           data["invoice_date"]),
                  **{k: v for k, v in data.items() if k in (
                      "doc_type", "supplier_id", "supplier_number", "invoice_date", "reception_date", "order_id",
                      "receipt_refs", "origin_invoice_id", "declared_total_ttc", "description", "source")})
    inv.lines = []
    _fill(ctx, inv, data, lines)
    inv.workflow_status = "brouillon"
    ctx.db.add(inv)
    ctx.db.flush()
    inv.anomalies = run_controls(ctx, inv)
    ctx_audit(ctx, "creation", "facture", inv.id, {"ref": inv.internal_ref, "ttc": inv.total_ttc})
    return inv


def update_invoice(ctx: Ctx, inv: Invoice, data: dict) -> Invoice:
    if inv.workflow_status != "brouillon":
        raise BusinessError("Seule une facture en brouillon est modifiable. Une facture validée se corrige par avoir ou annulation.")
    data = dict(data)
    lines = data.pop("lines", None) or [
        {"order_line_id": l.order_line_id, "item_ref": l.item_ref, "description": l.description,
         "quantity": l.quantity, "unit_price": l.unit_price, "tva_rate": l.tva_rate, "account_code": l.account_code}
        for l in inv.lines]
    for k in ("supplier_number", "invoice_date", "reception_date", "order_id", "receipt_refs",
              "declared_total_ttc", "description", "origin_invoice_id"):
        if k in data and data[k] is not None:
            setattr(inv, k, data[k])
    _fill(ctx, inv, data, lines)
    ctx.db.flush()
    inv.anomalies = run_controls(ctx, inv)
    ctx_audit(ctx, "modification", "facture", inv.id, {"ttc": inv.total_ttc})
    return inv


# ------------------------------------------------------------------ contrôles
def _a(code, gravite, message, ligne=None):
    return {"code": code, "gravite": gravite, "message": message, "ligne": ligne}


def run_controls(ctx: Ctx, inv: Invoice) -> list[dict]:
    db, cid = ctx.db, ctx.company_id
    out: list[dict] = []
    sup = db.get(Supplier, inv.supplier_id)
    tol_qty = setting_dec(db, cid, "tolerance_qte_pct")
    tol_price = setting_dec(db, cid, "tolerance_prix_pct")
    tol_abs = setting_dec(db, cid, "tolerance_montant_abs")

    # Fournisseur
    if sup.status != "actif":
        out.append(_a("FOURNISSEUR_NON_AUTORISE", "bloquante", f"Fournisseur {sup.code} au statut « {sup.status} »."))
    # Doublons
    others = db.scalars(select(Invoice).where(
        Invoice.company_id == cid, Invoice.supplier_id == inv.supplier_id, Invoice.id != inv.id,
        Invoice.workflow_status != "annulee", Invoice.doc_type == inv.doc_type))
    for o in others:
        if o.number_normalized == inv.number_normalized:
            out.append(_a("DOUBLON", "bloquante", f"Même numéro que {o.internal_ref} ({o.supplier_number})."))
        elif D(o.total_ttc) == D(inv.total_ttc) and abs((o.invoice_date - inv.invoice_date).days) <= 10:
            out.append(_a("DOUBLON_SUSPECT", "avertissement",
                          f"Même montant et date proche de {o.internal_ref} (n° {o.supplier_number})."))
    # Dates
    if inv.invoice_date > date.today():
        out.append(_a("DATE_FUTURE", "bloquante", "Date de facture postérieure à aujourd'hui."))
    if inv.reception_date and inv.reception_date < inv.invoice_date:
        out.append(_a("DATE_RECEPTION", "avertissement", "Date de réception antérieure à la date de facture."))
    # Calculs
    for i, l in enumerate(inv.lines, 1):
        if abs(r3(D(l.quantity) * D(l.unit_price)) - D(l.amount_ht)) > tol_abs:
            out.append(_a("ERREUR_CALCUL", "bloquante", f"Montant HT ≠ quantité × prix unitaire.", i))
        if abs(pct(l.amount_ht, l.tva_rate) - D(l.amount_tva)) > tol_abs:
            out.append(_a("TVA_INCOHERENTE", "bloquante", f"TVA ligne ≠ base × taux.", i))
    if inv.declared_total_ttc is not None and abs(D(inv.declared_total_ttc) - D(inv.total_ttc)) > tol_abs:
        out.append(_a("ERREUR_CALCUL", "bloquante",
                      f"Total TTC déclaré ({inv.declared_total_ttc}) ≠ total recalculé ({inv.total_ttc})."))
    # TVA
    allowed = {D(t.rate) for t in tax_rates(db, cid, "TVA", inv.invoice_date)}
    for i, l in enumerate(inv.lines, 1):
        if allowed and D(l.tva_rate) not in allowed:
            out.append(_a("TVA_INCOHERENTE", "bloquante", f"Taux de TVA {l.tva_rate} % non en vigueur.", i))
    if sup.vat_regime in ("non_assujetti", "exonere") and D(inv.total_tva) > 0:
        out.append(_a("TVA_INCOHERENTE", "bloquante",
                      f"Fournisseur {sup.vat_regime.replace('_', ' ')} : TVA facturée non déductible / anormale."))
    # Justificatif
    n_att = db.scalar(select(func.count(Attachment.id)).where(
        Attachment.company_id == cid, Attachment.entity == "facture", Attachment.entity_id == inv.id))
    if not n_att:
        grav = "bloquante" if setting_bool(db, cid, "justificatif_obligatoire") else "avertissement"
        out.append(_a("SANS_JUSTIFICATIF", grav, "Aucune pièce justificative jointe."))
    # Rapprochement à 3 niveaux
    if inv.doc_type == "facture":
        if not inv.order_id:
            seuil = setting_dec(db, cid, "seuil_bc_obligatoire")
            grav = "bloquante" if D(inv.total_ttc_tnd) >= seuil else "avertissement"
            out.append(_a("SANS_BC", grav, "Facture sans bon de commande préalable."))
        else:
            po = db.get(PurchaseOrder, inv.order_id)
            if po.supplier_id != inv.supplier_id:
                out.append(_a("BC_AUTRE_FOURNISSEUR", "bloquante", "Le bon de commande appartient à un autre fournisseur."))
            if po.status not in ("approuvee", "partiellement_recue", "recue", "cloturee"):
                out.append(_a("BC_NON_APPROUVE", "bloquante", f"Bon de commande au statut « {po.status} »."))
            if po.currency != inv.currency:
                out.append(_a("DEVISE", "bloquante", "Devise différente de celle du bon de commande."))
            po_line_ids = {l.id for l in po.lines}
            for i, l in enumerate(inv.lines, 1):
                if not l.order_line_id:
                    out.append(_a("LIGNE_HORS_BC", "avertissement", "Ligne non rattachée au bon de commande.", i))
                    continue
                if l.order_line_id not in po_line_ids:
                    out.append(_a("REFERENCE", "bloquante", "Ligne rattachée à une ligne d'un autre bon de commande.", i))
                    continue
                pol = db.get(PurchaseOrderLine, l.order_line_id)
                other_qty = D(db.scalar(
                    select(func.coalesce(func.sum(InvoiceLine.quantity), 0))
                    .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
                    .where(InvoiceLine.order_line_id == pol.id, Invoice.id != inv.id,
                           Invoice.doc_type == "facture", Invoice.workflow_status.in_(ACTIVE_WF))))
                credited = D(db.scalar(
                    select(func.coalesce(func.sum(InvoiceLine.quantity), 0))
                    .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
                    .where(InvoiceLine.order_line_id == pol.id, Invoice.doc_type == "avoir",
                           Invoice.workflow_status == "validee")))
                total_inv = other_qty - credited + D(l.quantity)
                if total_inv > D(pol.qty_received) * (1 + tol_qty / 100):
                    out.append(_a("QTE_NON_RECEPTIONNEE", "bloquante",
                                  f"Quantité facturée cumulée {total_inv} > quantité réceptionnée {pol.qty_received}.", i))
                if total_inv > D(pol.quantity) * (1 + tol_qty / 100):
                    out.append(_a("QTE_SUP_COMMANDE", "bloquante",
                                  f"Quantité facturée cumulée {total_inv} > quantité commandée {pol.quantity}.", i))
                if D(pol.unit_price) > 0:
                    ecart = (D(l.unit_price) - D(pol.unit_price)) / D(pol.unit_price) * 100
                    if ecart > tol_price:
                        out.append(_a("ECART_PRIX", "bloquante",
                                      f"Prix facturé {l.unit_price} vs commandé {pol.unit_price} (+{ecart:.2f} %).", i))
                    elif ecart != 0:
                        out.append(_a("ECART_PRIX", "avertissement",
                                      f"Écart de prix {ecart:.2f} % dans la tolérance.", i))
                if D(l.tva_rate) != D(pol.tva_rate):
                    out.append(_a("TVA_INCOHERENTE", "bloquante", "Taux de TVA différent de la commande.", i))
            other_ht = D(db.scalar(select(func.coalesce(func.sum(Invoice.total_ht), 0)).where(
                Invoice.order_id == po.id, Invoice.id != inv.id, Invoice.doc_type == "facture",
                Invoice.workflow_status.in_(ACTIVE_WF))))
            if other_ht + D(inv.total_ht) > D(po.total_ht) * (1 + tol_price / 100) + tol_abs:
                out.append(_a("DEPASSEMENT_BC", "bloquante",
                              f"Montant facturé cumulé HT {r3(other_ht + D(inv.total_ht))} > montant commandé {po.total_ht}."))
    # Prix anormal vs historique
    seuil_prix = setting_dec(db, cid, "seuil_hausse_prix_pct")
    for i, l in enumerate(inv.lines, 1):
        crit = (InvoiceLine.item_ref == l.item_ref) if l.item_ref else (
            func.lower(InvoiceLine.description) == l.description.lower())
        avg = db.scalar(select(func.avg(InvoiceLine.unit_price)).join(Invoice, Invoice.id == InvoiceLine.invoice_id)
                        .where(Invoice.supplier_id == inv.supplier_id, Invoice.id != inv.id,
                               Invoice.workflow_status == "validee", Invoice.doc_type == "facture", crit))
        if avg and D(avg) > 0 and (D(l.unit_price) - D(avg)) / D(avg) * 100 > seuil_prix:
            out.append(_a("PRIX_ANORMAL", "avertissement",
                          f"Prix {l.unit_price} supérieur de plus de {seuil_prix} % au prix moyen historique ({r3(avg)}).", i))
    # Plafond d'engagement
    if sup.credit_limit and inv.doc_type != "avoir":
        outstanding = sum((balance(db, o) * D(o.exchange_rate) for o in db.scalars(select(Invoice).where(
            Invoice.supplier_id == sup.id, Invoice.workflow_status == "validee", Invoice.id != inv.id))), ZERO)
        if outstanding + D(inv.total_ttc_tnd) > D(sup.credit_limit):
            out.append(_a("PLAFOND_FOURNISSEUR", "avertissement",
                          f"Encours fournisseur {r3(outstanding + D(inv.total_ttc_tnd))} TND > plafond {sup.credit_limit}."))
    # Avoir : rattachement
    if inv.doc_type == "avoir" and inv.origin_invoice_id:
        orig = db.get(Invoice, inv.origin_invoice_id)
        if not orig or orig.supplier_id != inv.supplier_id:
            out.append(_a("REFERENCE", "bloquante", "La facture d'origine de l'avoir est d'un autre fournisseur."))
    return out


def blocking(anomalies: list[dict] | None) -> list[dict]:
    return [a for a in (anomalies or []) if a["gravite"] == "bloquante"]


def _required_levels(ctx: Ctx, inv: Invoice) -> int:
    amt = D(inv.total_ttc_tnd)
    if amt >= setting_dec(ctx.db, ctx.company_id, "seuil_validation_n3"):
        return 3
    if amt >= setting_dec(ctx.db, ctx.company_id, "seuil_validation_n2"):
        return 2
    return 1


def submit_invoice(ctx: Ctx, inv: Invoice) -> Invoice:
    if inv.workflow_status != "brouillon":
        raise BusinessError("Seule une facture en brouillon peut être soumise à validation.")
    check_period_open(ctx.db, ctx.company_id, inv.invoice_date)
    inv.anomalies = run_controls(ctx, inv)
    inv.matching_status = "bloquant" if blocking(inv.anomalies) else ("ecarts" if inv.anomalies else "conforme")
    inv.required_levels = _required_levels(ctx, inv)
    inv.approved_levels = 0
    inv.workflow_status = "en_attente_validation"
    ctx_audit(ctx, "soumission", "facture", inv.id,
              {"anomalies": [a["code"] for a in inv.anomalies], "niveaux_requis": inv.required_levels})
    return inv


def _receivers(ctx: Ctx, inv: Invoice) -> set[int]:
    if not inv.order_id:
        return set()
    return {r.received_by_id for r in ctx.db.scalars(
        select(GoodsReceipt).where(GoodsReceipt.order_id == inv.order_id)) if r.received_by_id}


def approve_invoice(ctx: Ctx, inv: Invoice, comment: str | None = None, force: bool = False,
                    justification: str | None = None) -> Invoice:
    if inv.workflow_status != "en_attente_validation":
        raise BusinessError("La facture n'est pas en attente de validation.")
    level = inv.approved_levels + 1
    if ctx.user.role not in INVOICE_LEVEL_ROLES[level]:
        raise BusinessError(f"Niveau de validation {level} : profil {ctx.user.role} non habilité.",
                            code="niveau_insuffisant", status=403)
    if inv.created_by_id == ctx.user.id:
        raise BusinessError("Séparation des tâches : le saisisseur ne peut pas valider la facture.",
                            code="separation_taches", status=403)
    prior = {a.user_id for a in ctx.db.scalars(select(InvoiceApproval).where(
        InvoiceApproval.invoice_id == inv.id, InvoiceApproval.decision.in_(("approuve", "force"))))}
    if ctx.user.id in prior:
        raise BusinessError("Un même utilisateur ne peut valider deux niveaux.", code="separation_taches", status=403)
    if setting_bool(ctx.db, ctx.company_id, "separation_stricte") and ctx.user.id in _receivers(ctx, inv):
        raise BusinessError("Séparation des tâches : le réceptionnaire ne peut pas contrôler la facture.",
                            code="separation_taches", status=403)
    check_period_open(ctx.db, ctx.company_id, inv.invoice_date)
    inv.anomalies = run_controls(ctx, inv)
    blk = blocking(inv.anomalies)
    decision = "approuve"
    if blk and inv.forced:
        decision = "approuve"  # anomalies déjà levées par dérogation motivée du DAF au niveau précédent
    elif blk:
        if not force:
            raise BusinessError("Anomalies bloquantes non résolues : " + "; ".join(a["message"] for a in blk),
                                code="anomalies_bloquantes", data=blk)
        if not has_permission(ctx.user.role, "invoice.force"):
            raise BusinessError("Seul le Directeur financier peut forcer une validation malgré des anomalies.",
                                code="niveau_insuffisant", status=403)
        if not justification or len(justification.strip()) < 15:
            raise BusinessError("Justification détaillée obligatoire (15 caractères minimum) pour forcer la validation.")
        inv.forced, inv.force_justification, decision = True, justification, "force"
    ctx.db.add(InvoiceApproval(company_id=ctx.company_id, invoice_id=inv.id, level=level,
                               user_id=ctx.user.id, decision=decision, comment=comment or justification))
    inv.approved_levels = level
    ctx_audit(ctx, "validation_niveau", "facture", inv.id,
              {"niveau": level, "decision": decision, "justification": justification})
    if inv.approved_levels >= inv.required_levels:
        _finalize(ctx, inv)
    return inv


def _finalize(ctx: Ctx, inv: Invoice) -> None:
    inv.workflow_status = "validee"
    inv.validated_at = datetime.utcnow()
    sign = -1 if inv.doc_type == "avoir" else 1
    if inv.doc_type in ("facture", "avoir"):
        for l in inv.lines:
            if l.order_line_id:
                pol = ctx.db.get(PurchaseOrderLine, l.order_line_id)
                pol.qty_invoiced = r3(D(pol.qty_invoiced) + sign * D(l.quantity))
    accounting.post_invoice(ctx, inv)
    ctx_audit(ctx, "validation_definitive", "facture", inv.id, {"ref": inv.internal_ref})


def reject_invoice(ctx: Ctx, inv: Invoice, comment: str) -> Invoice:
    if inv.workflow_status != "en_attente_validation":
        raise BusinessError("La facture n'est pas en attente de validation.")
    if not has_permission(ctx.user.role, "invoice.validate"):
        raise BusinessError("Droit insuffisant.", status=403)
    ctx.db.add(InvoiceApproval(company_id=ctx.company_id, invoice_id=inv.id, level=inv.approved_levels + 1,
                               user_id=ctx.user.id, decision="rejete", comment=comment))
    inv.workflow_status, inv.approved_levels = "brouillon", 0
    ctx_audit(ctx, "rejet", "facture", inv.id, {"motif": comment})
    return inv


def cancel_invoice(ctx: Ctx, inv: Invoice, reason: str) -> Invoice:
    if not reason or len(reason.strip()) < 5:
        raise BusinessError("Motif d'annulation obligatoire.")
    if inv.workflow_status == "annulee":
        raise BusinessError("Facture déjà annulée.")
    if inv.workflow_status == "validee":
        if not has_permission(ctx.user.role, "invoice.cancel"):
            raise BusinessError("Annulation d'une facture validée réservée au DAF / responsable comptable.", status=403)
        active_alloc = ctx.db.scalar(select(func.count(PaymentAllocation.id)).where(
            PaymentAllocation.invoice_id == inv.id, PaymentAllocation.cancelled.is_(False)))
        active_cred = ctx.db.scalar(select(func.count(CreditAllocation.id)).where(
            ((CreditAllocation.target_invoice_id == inv.id) | (CreditAllocation.source_invoice_id == inv.id)),
            CreditAllocation.cancelled.is_(False)))
        if active_alloc or active_cred:
            raise BusinessError("Facture réglée ou lettrée : annulation impossible. Enregistrez un avoir.")
        sign = -1 if inv.doc_type == "avoir" else 1
        for l in inv.lines:
            if l.order_line_id and inv.doc_type in ("facture", "avoir"):
                pol = ctx.db.get(PurchaseOrderLine, l.order_line_id)
                pol.qty_invoiced = r3(D(pol.qty_invoiced) - sign * D(l.quantity))
        accounting.reverse_source(ctx, "facture", inv.id, date.today(), f"Annulation {inv.internal_ref} : {reason}")
    old = inv.workflow_status
    inv.workflow_status, inv.cancel_reason, inv.cancelled_at = "annulee", reason, date.today()
    ctx_audit(ctx, "annulation", "facture", inv.id, {"statut_avant": old, "motif": reason})
    return inv


# ------------------------------------------------------------------ avoirs et acomptes
def available_credit(db, src: Invoice) -> Decimal:
    if src.doc_type == "avoir":
        return r3(D(src.total_ttc) - consumed_credit(db, src))
    if src.doc_type == "acompte":  # part payée de l'acompte (hors timbre) non encore imputée
        paid = settled_amount(db, src)
        cap = min(paid, D(src.total_ht) + D(src.total_tva))
        return r3(cap - consumed_credit(db, src))
    return ZERO


def allocate_credit(ctx: Ctx, source: Invoice, target: Invoice, amount, on: date) -> CreditAllocation:
    amount = r3(amount)
    if source.doc_type not in ("avoir", "acompte"):
        raise BusinessError("Seul un avoir ou une facture d'acompte peut être imputé.")
    if source.workflow_status != "validee" or target.workflow_status != "validee":
        raise BusinessError("Avoir/acompte et facture cible doivent être validés.")
    if target.doc_type != "facture":
        raise BusinessError("La cible doit être une facture.")
    if source.supplier_id != target.supplier_id or source.currency != target.currency:
        raise BusinessError("Même fournisseur et même devise exigés.")
    if amount <= 0:
        raise BusinessError("Montant d'imputation invalide.")
    if amount > available_credit(ctx.db, source):
        raise BusinessError(f"Montant supérieur au disponible ({available_credit(ctx.db, source)}).")
    if amount > balance(ctx.db, target):
        raise BusinessError(f"Montant supérieur au solde de la facture ({balance(ctx.db, target)}).")
    check_period_open(ctx.db, ctx.company_id, on)
    ca = CreditAllocation(company_id=ctx.company_id, kind=source.doc_type, source_invoice_id=source.id,
                          target_invoice_id=target.id, amount=amount, allocation_date=on, created_by_id=ctx.user.id)
    ctx.db.add(ca)
    ctx.db.flush()
    if source.doc_type == "acompte":
        accounting.post_acompte_imputation(ctx, ca, source, target)
    ctx_audit(ctx, "imputation_" + source.doc_type, "facture", target.id,
              {"source": source.internal_ref, "montant": amount})
    return ca
