"""Modules 5, 8, 10, 11 — Échéancier, balance âgée, grand livre auxiliaire, indicateurs,
prévisions de décaissements, optimisation des paiements, risques fournisseurs, alertes.

Conventions documentées dans docs/05-indicateurs.md. Tous les montants sont en TND
(conversion au cours historique de la facture).
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from ..models import (CreditAllocation, Dispute, GoodsReceipt, Invoice, Payment, PaymentAllocation,
                      PurchaseOrder, Supplier, SupplierBankAccount, SupplierContract, SupplierEvaluation,
                      SupplierIncident)
from ..money import D, ZERO, r3
from ..security import Ctx
from . import accounting
from .common import setting_dec
from .invoices import balance, consumed_credit, disputed_amount, has_open_dispute
from .payments import planned_amount, treasury_available, unallocated
from .purchasing import commitments

BUCKETS = [("non_echu", None, 0), ("1_30", 1, 30), ("31_60", 31, 60), ("61_90", 61, 90),
           ("91_180", 91, 180), ("plus_180", 181, None)]


def _validated(ctx: Ctx, as_of: date | None = None, doc_types=("facture", "acompte")):
    q = select(Invoice).where(Invoice.company_id == ctx.company_id, Invoice.validated_at.is_not(None),
                              Invoice.doc_type.in_(doc_types))
    if as_of:
        q = q.where(Invoice.invoice_date <= as_of)
    return list(ctx.db.scalars(q))


def _pc(x) -> str:
    """Pourcentage lisible : 2.0000 -> « 2 », 1.5000 -> « 1,5 »."""
    return format(D(x).normalize(), "f").replace(".", ",")


def bucket_of(as_of: date, due: date | None) -> str:
    late = (as_of - due).days if due else 0
    for name, lo, hi in BUCKETS:
        if lo is None and late <= 0:
            return name
        if lo is not None and late >= lo and (hi is None or late <= hi):
            return name
    return "non_echu"


# ------------------------------------------------------------ balance âgée
def aged_balance(ctx: Ctx, as_of: date, supplier_id: int | None = None, currency: str | None = None,
                 category: str | None = None) -> dict:
    rows: dict[int, dict] = {}
    details = []
    sups = {s.id: s for s in ctx.db.scalars(select(Supplier).where(Supplier.company_id == ctx.company_id))}

    def row(sid):
        s = sups[sid]
        return rows.setdefault(sid, {"supplier_id": sid, "code": s.code, "fournisseur": s.legal_name,
                                     "categorie": s.category, **{b[0]: ZERO for b in BUCKETS},
                                     "avoirs_non_imputes": ZERO, "avances_non_imputees": ZERO,
                                     "total_brut": ZERO, "total_net": ZERO, "dont_litiges": ZERO})

    def keep(inv_sup, cur):
        s = sups[inv_sup]
        return ((not supplier_id or inv_sup == supplier_id) and (not currency or cur == currency)
                and (not category or s.category == category))

    for inv in _validated(ctx, as_of):
        if not keep(inv.supplier_id, inv.currency):
            continue
        bal = balance(ctx.db, inv, as_of)
        if bal <= 0:
            continue
        tnd = r3(bal * D(inv.exchange_rate))
        b = bucket_of(as_of, inv.due_date)
        r = row(inv.supplier_id)
        r[b] += tnd
        r["total_brut"] += tnd
        lit = r3(disputed_amount(ctx.db, inv) * D(inv.exchange_rate)) if has_open_dispute(ctx.db, inv) else ZERO
        r["dont_litiges"] += min(lit, tnd)
        details.append({"invoice_id": inv.id, "ref": inv.internal_ref, "numero": inv.supplier_number,
                        "fournisseur": sups[inv.supplier_id].legal_name, "date": inv.invoice_date,
                        "echeance": inv.due_date, "devise": inv.currency, "solde_devise": bal, "solde_tnd": tnd,
                        "retard_jours": max((as_of - inv.due_date).days, 0) if inv.due_date else 0, "tranche": b})
    for av in _validated(ctx, as_of, ("avoir",)):
        if not keep(av.supplier_id, av.currency):
            continue
        rem = r3(D(av.total_ttc) - consumed_credit(ctx.db, av, as_of))
        if rem > 0:
            row(av.supplier_id)["avoirs_non_imputes"] -= r3(rem * D(av.exchange_rate))
    for p in ctx.db.scalars(select(Payment).where(Payment.company_id == ctx.company_id,
                                                  Payment.status.in_(("emis", "debite")),
                                                  Payment.payment_date <= as_of)):
        if not keep(p.supplier_id, p.currency):
            continue
        used = sum((D(a.amount) for a in p.allocations if not a.cancelled and a.allocation_date <= as_of), ZERO)
        rest = r3(D(p.cash_amount) + D(p.rs_amount) - used)
        if rest > 0:
            row(p.supplier_id)["avances_non_imputees"] -= r3(rest * D(p.exchange_rate))
    for r in rows.values():
        r["total_net"] = r3(r["total_brut"] + r["avoirs_non_imputes"] + r["avances_non_imputees"])
    out_rows = sorted(rows.values(), key=lambda x: -x["total_brut"])
    totals = {k: r3(sum((r[k] for r in out_rows), ZERO)) for k in
              [b[0] for b in BUCKETS] + ["avoirs_non_imputes", "avances_non_imputees", "total_brut", "total_net", "dont_litiges"]}
    return {"date_arrete": as_of, "lignes": out_rows, "totaux": totals,
            "details": sorted(details, key=lambda d: (d["echeance"] or as_of))}


# ------------------------------------------------------------ grand livre / balance auxiliaire
def ledger_movements(ctx: Ctx, supplier_id: int | None = None, date_to: date | None = None) -> list[dict]:
    """Mouvements du compte fournisseur (401/404) reconstitués à partir des pièces de gestion."""
    mv = []
    cid = ctx.company_id
    sups = {s.id: s for s in ctx.db.scalars(select(Supplier).where(Supplier.company_id == cid))}
    for inv in _validated(ctx, None, ("facture", "acompte", "avoir")):
        if supplier_id and inv.supplier_id != supplier_id:
            continue
        amt = D(inv.total_ttc_tnd)
        dr, cr = (amt, ZERO) if inv.doc_type == "avoir" else (ZERO, amt)
        mv.append({"date": inv.invoice_date, "supplier_id": inv.supplier_id, "piece": inv.internal_ref,
                   "type": inv.doc_type, "libelle": f"{inv.doc_type.capitalize()} n°{inv.supplier_number}",
                   "debit": dr, "credit": cr})
        if inv.workflow_status == "annulee" and inv.cancelled_at:
            mv.append({"date": inv.cancelled_at, "supplier_id": inv.supplier_id, "piece": inv.internal_ref,
                       "type": "annulation", "libelle": f"Annulation {inv.internal_ref}", "debit": cr, "credit": dr})
    for p in ctx.db.scalars(select(Payment).where(Payment.company_id == cid,
                                                  Payment.status.in_(("emis", "debite", "rejete")))):
        if supplier_id and p.supplier_id != supplier_id:
            continue
        if p.status == "rejete" and not p.executed_by_id:
            continue
        initial = [a for a in p.allocations if not a.deferred]
        if p.kind == "reglement":
            amt = r3(sum((D(a.amount) * D(ctx.db.get(Invoice, a.invoice_id).exchange_rate) for a in initial), ZERO)
                     + (D(p.cash_amount) + D(p.rs_amount) - sum((D(a.amount) for a in initial), ZERO)) * D(p.exchange_rate))
        else:
            amt = ZERO
        if amt:
            mv.append({"date": p.payment_date, "supplier_id": p.supplier_id, "piece": p.number, "type": "reglement",
                       "libelle": f"Règlement {p.method} {p.reference or ''}".strip(), "debit": amt, "credit": ZERO})
            if p.status == "rejete":
                mv.append({"date": p.rejected_date, "supplier_id": p.supplier_id, "piece": p.number, "type": "rejet",
                           "libelle": f"Rejet {p.method} {p.reference or ''}".strip(), "debit": ZERO, "credit": amt})
        for a in p.allocations:
            if a in initial and p.kind == "reglement":
                continue
            inv = ctx.db.get(Invoice, a.invoice_id)
            hist = r3(D(a.amount) * D(inv.exchange_rate))
            if p.kind == "avance":
                mv.append({"date": a.allocation_date, "supplier_id": p.supplier_id, "piece": p.number,
                           "type": "imputation_avance", "libelle": f"Imputation avance sur {inv.internal_ref}",
                           "debit": hist, "credit": ZERO})
                if p.status == "rejete":
                    mv.append({"date": p.rejected_date, "supplier_id": p.supplier_id, "piece": p.number,
                               "type": "rejet", "libelle": "Rejet avance", "debit": ZERO, "credit": hist})
            elif D(a.fx_difference_tnd):
                fx = D(a.fx_difference_tnd)
                mv.append({"date": a.allocation_date, "supplier_id": p.supplier_id, "piece": p.number,
                           "type": "ecart_change", "libelle": f"Écart de change {inv.internal_ref}",
                           "debit": -fx if fx < 0 else ZERO, "credit": fx if fx > 0 else ZERO})
    for ca in ctx.db.scalars(select(CreditAllocation).where(CreditAllocation.company_id == cid,
                                                            CreditAllocation.kind == "acompte",
                                                            CreditAllocation.cancelled.is_(False))):
        src = ctx.db.get(Invoice, ca.source_invoice_id)
        if supplier_id and src.supplier_id != supplier_id:
            continue
        mv.append({"date": ca.allocation_date, "supplier_id": src.supplier_id, "piece": src.internal_ref,
                   "type": "imputation_acompte", "libelle": "Imputation acompte",
                   "debit": r3(D(ca.amount) * D(src.exchange_rate)), "credit": ZERO})
    mv = [m for m in mv if not date_to or m["date"] <= date_to]
    mv.sort(key=lambda m: (m["supplier_id"], m["date"], m["piece"]))
    run: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for m in mv:
        run[m["supplier_id"]] += m["credit"] - m["debit"]
        m["solde"] = r3(run[m["supplier_id"]])
        m["fournisseur"] = sups[m["supplier_id"]].legal_name
    return mv


def trial_balance(ctx: Ctx, date_from: date, date_to: date) -> dict:
    sups = {s.id: s for s in ctx.db.scalars(select(Supplier).where(Supplier.company_id == ctx.company_id))}
    acc: dict[int, dict] = {}
    for m in ledger_movements(ctx, None, date_to):
        r = acc.setdefault(m["supplier_id"], {"supplier_id": m["supplier_id"], "code": sups[m["supplier_id"]].code,
                                              "fournisseur": sups[m["supplier_id"]].legal_name, "solde_initial": ZERO,
                                              "debit": ZERO, "credit": ZERO, "solde_final": ZERO})
        if m["date"] < date_from:
            r["solde_initial"] += m["credit"] - m["debit"]
        else:
            r["debit"] += m["debit"]
            r["credit"] += m["credit"]
    rows = []
    for r in acc.values():
        r["solde_final"] = r3(r["solde_initial"] + r["credit"] - r["debit"])
        rows.append({k: (r3(v) if isinstance(v, Decimal) else v) for k, v in r.items()})
    rows.sort(key=lambda r: r["code"])
    tot = {k: r3(sum((r[k] for r in rows), ZERO)) for k in ("solde_initial", "debit", "credit", "solde_final")}
    return {"du": date_from, "au": date_to, "lignes": rows, "totaux": tot}


def reconcile_aux_gl(ctx: Ctx, as_of: date, external_gl_balance: Decimal | None = None) -> dict:
    """Rapprochement auxiliaire fournisseurs (pièces) / comptabilité générale (écritures 401+404)."""
    aux: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for m in ledger_movements(ctx, None, as_of):
        aux[m["supplier_id"]] += m["credit"] - m["debit"]
    from .common import account
    prefixes = {account(ctx.db, ctx.company_id, "fournisseurs"), account(ctx.db, ctx.company_id, "fournisseurs_immo")}
    gl_all = sum((accounting.account_balance(ctx, p, as_of) for p in prefixes), ZERO)
    gl_val = sum((accounting.account_balance(ctx, p, as_of, only_validated=True) for p in prefixes), ZERO)
    total_aux = r3(sum(aux.values(), ZERO))
    ecarts = []
    for sid, a in aux.items():
        g = sum((accounting.account_balance(ctx, p, as_of, supplier_id=sid) for p in prefixes), ZERO)
        if r3(a) != r3(g):
            s = ctx.db.get(Supplier, sid)
            ecarts.append({"supplier_id": sid, "fournisseur": s.legal_name, "auxiliaire": r3(a), "general": r3(g),
                           "ecart": r3(a - g)})
    res = {"date_arrete": as_of, "solde_auxiliaire": total_aux, "solde_general_toutes_ecritures": r3(gl_all),
           "solde_general_ecritures_validees": r3(gl_val), "ecart": r3(total_aux - gl_all),
           "concordant": r3(total_aux - gl_all) == 0 and not ecarts, "ecarts_par_fournisseur": ecarts,
           "ecritures_non_validees": r3(gl_all - gl_val)}
    if external_gl_balance is not None:
        res["solde_logiciel_comptable_externe"] = r3(external_gl_balance)
        res["ecart_externe"] = r3(total_aux - D(external_gl_balance))
    return res


# ------------------------------------------------------------ indicateurs
def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def kpis(ctx: Ctx, as_of: date, period_days: int = 365) -> dict:
    start = as_of - timedelta(days=period_days)
    invs = _validated(ctx, as_of)
    total = echu = non_echu = litige = ZERO
    by_sup: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for inv in invs:
        bal = r3(balance(ctx.db, inv, as_of) * D(inv.exchange_rate))
        if bal <= 0:
            continue
        total += bal
        by_sup[inv.supplier_id] += bal
        if inv.due_date and inv.due_date < as_of:
            echu += bal
        else:
            non_echu += bal
        if has_open_dispute(ctx.db, inv):
            litige += min(bal, r3(disputed_amount(ctx.db, inv) * D(inv.exchange_rate)))
    avoirs = _validated(ctx, as_of, ("avoir",))
    purchases = sum((D(i.total_ttc_tnd) for i in invs if i.invoice_date > start and i.doc_type == "facture"), ZERO) \
        - sum((D(a.total_ttc_tnd) for a in avoirs if a.invoice_date > start), ZERO)
    dpo = r3(total / purchases * period_days) if purchases > 0 else None
    # délais et ponctualité (paiements de la période)
    w_days = w_amt = on_time = ZERO
    q = (select(PaymentAllocation, Payment, Invoice)
         .join(Payment, Payment.id == PaymentAllocation.payment_id)
         .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
         .where(Payment.company_id == ctx.company_id, Payment.status.in_(("emis", "debite")),
                PaymentAllocation.cancelled.is_(False), PaymentAllocation.allocation_date > start,
                PaymentAllocation.allocation_date <= as_of))
    n_pay = 0
    for a, p, inv in ctx.db.execute(q):
        amt = D(a.amount) * D(inv.exchange_rate)
        w_days += amt * (a.allocation_date - inv.invoice_date).days
        w_amt += amt
        n_pay += 1
        if inv.due_date and a.allocation_date <= inv.due_date:
            on_time += amt
    n_inv = len([i for i in invs if i.invoice_date > start and i.doc_type == "facture"])
    n_disp = ctx.db.scalar(select(func.count(func.distinct(Dispute.invoice_id))).join(
        Invoice, Invoice.id == Dispute.invoice_id).where(
        Dispute.company_id == ctx.company_id, Invoice.invoice_date > start, Invoice.invoice_date <= as_of))
    comm = commitments(ctx)
    top = sorted(by_sup.items(), key=lambda kv: -kv[1])
    sups = {s.id: s for s in ctx.db.scalars(select(Supplier).where(Supplier.company_id == ctx.company_id))}
    hhi = r3(sum(((v / total * 100) ** 2 for v in by_sup.values()), ZERO)) if total else ZERO
    evolution = []
    y, m = as_of.year, as_of.month
    for _ in range(12):
        me = min(month_end(y, m), as_of)
        tot_m = sum((max(r3(balance(ctx.db, i, me) * D(i.exchange_rate)), ZERO) for i in invs if i.invoice_date <= me), ZERO)
        evolution.append({"mois": f"{y}-{m:02d}", "dettes": r3(tot_m)})
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    evolution.reverse()
    pending = ctx.db.scalar(select(func.count(Invoice.id)).where(
        Invoice.company_id == ctx.company_id, Invoice.workflow_status == "en_attente_validation"))
    return {
        "date_arrete": as_of, "periode_jours": period_days,
        "total_dettes": r3(total), "dettes_echues": r3(echu), "dettes_non_echues": r3(non_echu),
        "dettes_en_litige": r3(litige),
        "achats_ttc_periode": r3(purchases), "dpo_jours": dpo,
        "delai_moyen_paiement_jours": r3(w_days / w_amt) if w_amt else None,
        "taux_paiement_a_echeance_pct": r3(on_time / w_amt * 100) if w_amt else None,
        "nombre_paiements_analyses": n_pay,
        "taux_factures_litigieuses_pct": r3(D(n_disp) / n_inv * 100) if n_inv else None,
        "engagements_non_factures": r3(sum((c["restant_ttc_tnd"] for c in comm), ZERO)),
        "factures_en_attente_validation": pending,
        "concentration_top5_pct": r3(sum((v for _, v in top[:5]), ZERO) / total * 100) if total else None,
        "indice_hhi": hhi,
        "principaux_creanciers": [{"supplier_id": sid, "fournisseur": sups[sid].legal_name, "montant": r3(v),
                                   "part_pct": r3(v / total * 100) if total else ZERO} for sid, v in top[:10]],
        "evolution_mensuelle": evolution,
    }


# ------------------------------------------------------------ prévisions
HORIZONS = (7, 30, 60, 90, 365)


def forecast(ctx: Ctx, as_of: date) -> dict:
    items = []
    for inv in _validated(ctx, None):
        bal = balance(ctx.db, inv)
        if bal <= 0:
            continue
        rate = D(inv.exchange_rate)
        disp = min(disputed_amount(ctx.db, inv), bal) if has_open_dispute(ctx.db, inv) else ZERO
        cash_part = (bal - disp) * (1 - (D(inv.rs_amount) / D(inv.total_ttc) if D(inv.total_ttc) else 0))
        due = max(inv.due_date or as_of, as_of)
        if bal - disp > 0:
            items.append({"date": due, "categorie": "certain", "source": "facture validée", "ref": inv.internal_ref,
                          "supplier_id": inv.supplier_id, "montant": r3(cash_part * rate),
                          "en_retard": bool(inv.due_date and inv.due_date < as_of)})
        if disp > 0:
            items.append({"date": due, "categorie": "conditionnel", "source": "montant en litige",
                          "ref": inv.internal_ref, "supplier_id": inv.supplier_id, "montant": r3(disp * rate)})
    for inv in ctx.db.scalars(select(Invoice).where(Invoice.company_id == ctx.company_id,
                                                    Invoice.workflow_status.in_(("brouillon", "en_attente_validation")),
                                                    Invoice.doc_type != "avoir")):
        items.append({"date": max(inv.due_date or as_of, as_of), "categorie": "probable",
                      "source": "facture en cours de validation", "ref": inv.internal_ref,
                      "supplier_id": inv.supplier_id, "montant": r3(D(inv.net_to_pay) * D(inv.exchange_rate))})
    for p in ctx.db.scalars(select(Payment).where(Payment.company_id == ctx.company_id, Payment.status == "emis")):
        items.append({"date": max(p.due_date or as_of, as_of), "categorie": "certain",
                      "source": f"{p.method} émis non débité", "ref": p.number, "supplier_id": p.supplier_id,
                      "montant": r3(D(p.cash_amount) * D(p.exchange_rate))})
    for c in commitments(ctx):
        exp = c["livraison_prevue"] or (c["date_commande"] + timedelta(days=30))
        items.append({"date": max(exp + timedelta(days=c["delai_paiement"] or 0), as_of), "categorie": "probable",
                      "source": "commande non facturée", "ref": c["numero"], "supplier_id": c["supplier_id"],
                      "montant": c["restant_ttc_tnd"]})
    end = as_of + timedelta(days=365)
    for k in ctx.db.scalars(select(SupplierContract).where(SupplierContract.company_id == ctx.company_id,
                                                           SupplierContract.status == "actif",
                                                           SupplierContract.frequency_months > 0)):
        d = k.next_due_date or as_of
        while d <= end and (not k.end_date or d <= k.end_date):
            if d >= as_of:
                items.append({"date": d, "categorie": "probable", "source": "contrat récurrent",
                              "ref": k.reference, "supplier_id": k.supplier_id, "montant": r3(k.recurring_amount_ttc)})
            m = d.month - 1 + k.frequency_months
            y = d.year + m // 12
            d = date(y, m % 12 + 1, min(d.day, calendar.monthrange(y, m % 12 + 1)[1]))
    horizons = []
    for h in HORIZONS:
        lim = as_of + timedelta(days=h)
        tot = {c: r3(sum((i["montant"] for i in items if i["date"] <= lim and i["categorie"] == c), ZERO))
               for c in ("certain", "probable", "conditionnel")}
        horizons.append({"jours": h, **tot, "total": r3(sum(tot.values(), ZERO))})
    monthly = []
    y, m = as_of.year, as_of.month
    for _ in range(12):
        lo, hi = date(y, m, 1), month_end(y, m)
        row = {c: r3(sum((i["montant"] for i in items if lo <= i["date"] <= hi and i["categorie"] == c), ZERO))
               for c in ("certain", "probable", "conditionnel")}
        monthly.append({"mois": f"{y}-{m:02d}", **row})
        m += 1
        if m == 13:
            y, m = y + 1, 1
    avail = treasury_available(ctx)
    return {"date": as_of, "tresorerie_disponible": avail, "horizons": horizons, "mensuel": monthly,
            "detail": sorted(items, key=lambda i: i["date"]),
            "conventions": "certain = factures validées non contestées + moyens de paiement émis non débités (nets de RS) ; "
                           "probable = factures en validation, commandes non facturées, contrats récurrents ; "
                           "conditionnel = montants en litige. Les retards sont positionnés à la date du jour."}


# ------------------------------------------------------------ optimisation des paiements
def payment_plan(ctx: Ctx, as_of: date, horizon_days: int = 30, cash_available: Decimal | None = None) -> dict:
    cost_of_funds = setting_dec(ctx.db, ctx.company_id, "cout_financement_pct")
    cash = D(cash_available) if cash_available is not None else treasury_available(ctx)
    lim = as_of + timedelta(days=horizon_days)
    cands = []
    for inv in _validated(ctx, None, ("facture", "acompte")):
        bal = balance(ctx.db, inv)
        if bal <= 0:
            continue
        sup = ctx.db.get(Supplier, inv.supplier_id)
        disp = disputed_amount(ctx.db, inv) if has_open_dispute(ctx.db, inv) else ZERO
        payable = r3(bal - disp - planned_amount(ctx.db, inv))
        rate = D(inv.exchange_rate)
        reasons, score = [], 0.0
        late = (as_of - inv.due_date).days if inv.due_date else 0
        rec = "payer_a_echeance"
        disc_deadline = inv.invoice_date + timedelta(days=sup.early_discount_days or 0)
        if payable <= 0:
            rec = "suspendu_litige" if disp > 0 else "deja_programme"
            reasons.append("Montant contesté : non payable avant résolution du litige." if disp > 0
                           else "Déjà inclus dans un paiement en préparation.")
        elif late > 0:
            rec = "payer_immediatement"
            score += 50 + min(late, 180) / 2
            reasons.append(f"Échue depuis {late} jours.")
            if D(sup.late_penalty_pct) > 0:
                pen = r3(payable * rate * D(sup.late_penalty_pct) / 100 * late / 365)
                score += 15
                reasons.append(f"Pénalités contractuelles estimées à ce jour : {pen} TND ({_pc(sup.late_penalty_pct)} %/an).")
        elif D(sup.early_discount_pct) > 0 and disc_deadline >= as_of:
            p_ = D(sup.early_discount_pct) / 100
            days_gained = max((inv.due_date - disc_deadline).days, 1) if inv.due_date else 30
            annual = r3(p_ / (1 - p_) * D(365) / D(days_gained) * 100)
            if annual > cost_of_funds:
                rec = "payer_anticipe_escompte"
                score += 40
                reasons.append(f"Escompte {_pc(sup.early_discount_pct)} % avant le {disc_deadline:%d/%m/%Y} : "
                               f"rendement annualisé {_pc(annual)} % > coût de financement {_pc(cost_of_funds)} %.")
            else:
                reasons.append(f"Escompte disponible mais rendement annualisé ({annual} %) inférieur au coût de financement.")
        elif inv.due_date and inv.due_date <= lim:
            score += 30 - max((inv.due_date - as_of).days, 0) / 2
            reasons.append(f"Échéance le {inv.due_date:%d/%m/%Y}.")
        else:
            rec = "hors_horizon"
            reasons.append("Échéance au-delà de l'horizon : paiement anticipé non justifié pour la trésorerie.")
        if sup.category in ("strategique", "critique"):
            score += 20
            reasons.append(f"Fournisseur {sup.category.replace('strategique', 'stratégique')} : priorité pour sécuriser l'approvisionnement.")
        cands.append({"invoice_id": inv.id, "ref": inv.internal_ref, "numero": inv.supplier_number,
                      "supplier_id": sup.id, "fournisseur": sup.legal_name, "categorie": sup.category,
                      "echeance": inv.due_date, "solde": bal, "payable": max(payable, ZERO),
                      "payable_tnd_net_rs": r3(max(payable, ZERO) * rate * (1 - (D(inv.rs_amount) / D(inv.total_ttc) if D(inv.total_ttc) else 0))),
                      "recommandation": rec, "score": round(score, 1), "justification": reasons})
    order = sorted([c for c in cands if c["recommandation"] in ("payer_immediatement", "payer_anticipe_escompte", "payer_a_echeance")],
                   key=lambda c: -c["score"])
    remaining = cash
    for c in order:
        if c["payable_tnd_net_rs"] <= remaining:
            c["retenu"] = True
            remaining -= c["payable_tnd_net_rs"]
        else:
            c["retenu"] = False
            if c["categorie"] not in ("strategique", "critique"):
                c["recommandation"] = "report_a_negocier"
                c["justification"].append(
                    "Trésorerie insuffisante : proposer au fournisseur un échéancier ou un report, "
                    "par accord écrit — ne jamais différer unilatéralement une dette exigible.")
            else:
                c["justification"].append("Trésorerie insuffisante : rechercher un financement court terme "
                                          "(facilité de caisse, escompte) plutôt que retarder un fournisseur critique.")
    for c in cands:
        c.setdefault("retenu", False)
    retained = [c for c in cands if c["retenu"]]
    return {"date": as_of, "horizon_jours": horizon_days, "tresorerie_disponible": r3(cash),
            "cout_financement_pct": cost_of_funds,
            "total_propose": r3(sum((c["payable_tnd_net_rs"] for c in retained), ZERO)),
            "tresorerie_apres_paiements": r3(remaining),
            "propositions": sorted(cands, key=lambda c: (-int(c["retenu"]), -c["score"])),
            "avertissement": "Proposition d'aide à la décision : la sélection finale et l'autorisation des "
                             "paiements restent de la responsabilité des signataires habilités."}


# ------------------------------------------------------------ risques fournisseurs
def supplier_risk(ctx: Ctx, as_of: date) -> list[dict]:
    db, cid = ctx.db, ctx.company_id
    start = as_of - timedelta(days=365)
    sups = list(db.scalars(select(Supplier).where(Supplier.company_id == cid)))
    purch: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for inv in _validated(ctx, as_of, ("facture",)):
        if inv.invoice_date > start:
            purch[inv.supplier_id] += D(inv.total_ttc_tnd)
    total_p = sum(purch.values(), ZERO)
    dep_threshold = setting_dec(db, cid, "seuil_dependance_pct")
    th_m, th_e, th_c = (setting_dec(db, cid, k) for k in ("risque_seuil_modere", "risque_seuil_eleve", "risque_seuil_critique"))
    out = []
    for s in sups:
        factors = []
        score = D(0)
        share = r3(purch[s.id] / total_p * 100) if total_p else ZERO
        if share >= dep_threshold:
            score += 25
            factors.append(f"Dépendance : {share} % des achats 12 mois (seuil {dep_threshold} %).")
        elif share >= dep_threshold / 2:
            score += 10
            factors.append(f"Poids significatif : {share} % des achats.")
        n_inv = db.scalar(select(func.count(Invoice.id)).where(Invoice.supplier_id == s.id, Invoice.invoice_date > start)) or 0
        n_disp = db.scalar(select(func.count(Dispute.id)).where(Dispute.supplier_id == s.id, Dispute.opened_at > start)) or 0
        if n_disp:
            rate = n_disp / max(n_inv, 1) * 100
            pts = min(20, 5 + rate / 2)
            score += D(str(round(pts, 2)))
            factors.append(f"{n_disp} litige(s) sur 12 mois ({rate:.0f} % des factures).")
        n_inc = db.scalar(select(func.count(SupplierIncident.id)).where(
            SupplierIncident.supplier_id == s.id, SupplierIncident.incident_date > start)) or 0
        if n_inc:
            score += min(15, 5 * n_inc)
            factors.append(f"{n_inc} incident(s) enregistré(s).")
        late_rec = 0
        for po in db.scalars(select(PurchaseOrder).where(PurchaseOrder.supplier_id == s.id, PurchaseOrder.expected_date.is_not(None),
                                                         PurchaseOrder.order_date > start)):
            first = db.scalar(select(func.min(GoodsReceipt.receipt_date)).where(GoodsReceipt.order_id == po.id))
            if (first and first > po.expected_date) or (not first and po.expected_date < as_of and po.status in ("approuvee",)):
                late_rec += 1
        if late_rec:
            score += min(15, 5 * late_rec)
            factors.append(f"{late_rec} livraison(s) en retard.")
        ev = db.scalar(select(SupplierEvaluation).where(SupplierEvaluation.supplier_id == s.id)
                       .order_by(SupplierEvaluation.id.desc()).limit(1))
        if ev:
            q = (ev.quality + ev.delivery + ev.compliance) / 3
            if q < 3:
                score += D(str(round((3 - q) * 7, 2)))
                factors.append(f"Évaluation moyenne {q:.1f}/5.")
            if ev.supply_risk >= 4:
                score += 10
                factors.append(f"Risque de rupture d'approvisionnement évalué {ev.supply_risk}/5.")
        if s.category in ("critique", "strategique") and score > 0:
            score += 10
            factors.append(f"Fournisseur {s.category} : l'impact d'une défaillance est amplifié.")
        if s.category == "a_risque":
            score += 15
            factors.append("Classé « à risque » par l'entreprise.")
        if not any(b.status == "verifie" for b in s.bank_accounts):
            factors.append("Aucun RIB vérifié.")
        score = min(score, D(100))
        level = ("critique" if score >= th_c else "eleve" if score >= th_e else "modere" if score >= th_m else "faible")
        out.append({"supplier_id": s.id, "code": s.code, "fournisseur": s.legal_name, "categorie": s.category,
                    "part_achats_pct": share, "achats_12m": r3(purch[s.id]), "score": r3(score),
                    "niveau": level, "facteurs": factors})
    return sorted(out, key=lambda r: -r["score"])


# ------------------------------------------------------------ alertes
def alerts(ctx: Ctx, as_of: date) -> list[dict]:
    db, cid = ctx.db, ctx.company_id
    out = []
    days = int(setting_dec(db, cid, "jours_alerte_echeance"))
    for inv in _validated(ctx, None):
        bal = balance(db, inv)
        if bal <= 0 or not inv.due_date:
            continue
        if inv.due_date < as_of:
            out.append({"type": "echue", "gravite": "haute", "ref": inv.internal_ref, "lien": f"/factures/{inv.id}",
                        "message": f"{inv.internal_ref} ({inv.supplier.legal_name}) échue depuis {(as_of - inv.due_date).days} j — solde {bal} {inv.currency}."})
        elif inv.due_date <= as_of + timedelta(days=days):
            out.append({"type": "echeance_proche", "gravite": "moyenne", "ref": inv.internal_ref, "lien": f"/factures/{inv.id}",
                        "message": f"{inv.internal_ref} ({inv.supplier.legal_name}) à échéance le {inv.due_date:%d/%m/%Y} — {bal} {inv.currency}."})
    n = db.scalar(select(func.count(Invoice.id)).where(Invoice.company_id == cid, Invoice.workflow_status == "en_attente_validation"))
    if n:
        out.append({"type": "validation", "gravite": "moyenne", "lien": "/factures?statut=en_attente_validation",
                    "message": f"{n} facture(s) en attente de validation."})
    n = db.scalar(select(func.count(Payment.id)).where(Payment.company_id == cid, Payment.status == "a_approuver"))
    if n:
        out.append({"type": "paiement", "gravite": "moyenne", "lien": "/reglements",
                    "message": f"{n} règlement(s) en attente d'autorisation."})
    for b in db.scalars(select(SupplierBankAccount).where(SupplierBankAccount.company_id == cid,
                                                          SupplierBankAccount.status == "a_verifier")):
        out.append({"type": "rib", "gravite": "haute", "lien": f"/fournisseurs/{b.supplier_id}",
                    "message": f"RIB à vérifier (contre-appel) pour {b.supplier.legal_name}."})
    for s in db.scalars(select(Supplier).where(Supplier.company_id == cid, Supplier.status == "en_attente")):
        out.append({"type": "fournisseur", "gravite": "basse", "lien": f"/fournisseurs/{s.id}",
                    "message": f"Fournisseur {s.code} {s.legal_name} en attente d'approbation."})
    for k in db.scalars(select(SupplierContract).where(SupplierContract.company_id == cid, SupplierContract.status == "actif",
                                                       SupplierContract.end_date.is_not(None))):
        if as_of <= k.end_date <= as_of + timedelta(days=k.notice_days):
            out.append({"type": "contrat", "gravite": "moyenne", "lien": f"/fournisseurs/{k.supplier_id}",
                        "message": f"Contrat {k.reference} arrive à échéance le {k.end_date:%d/%m/%Y}."})
    for p in db.scalars(select(Payment).where(Payment.company_id == cid, Payment.status == "emis",
                                              Payment.method == "cheque")):
        if (as_of - p.payment_date).days > 30:
            out.append({"type": "cheque", "gravite": "basse", "lien": f"/reglements/{p.id}",
                        "message": f"Chèque {p.reference or p.number} émis il y a {(as_of - p.payment_date).days} j, non encore présenté."})
    for d in db.scalars(select(Dispute).where(Dispute.company_id == cid, Dispute.status.in_(("ouvert", "en_cours")))):
        if (as_of - d.opened_at).days > 30:
            out.append({"type": "litige", "gravite": "moyenne", "lien": "/litiges",
                        "message": f"Litige {d.number} ouvert depuis {(as_of - d.opened_at).days} jours."})
    for inv in db.scalars(select(Invoice).where(Invoice.company_id == cid,
                                                Invoice.workflow_status.in_(("brouillon", "en_attente_validation")))):
        for a in inv.anomalies or []:
            if a["code"] in ("PRIX_ANORMAL", "DOUBLON", "DOUBLON_SUSPECT"):
                out.append({"type": "anomalie", "gravite": "haute" if a["code"] == "DOUBLON" else "moyenne",
                            "lien": f"/factures/{inv.id}", "message": f"{inv.internal_ref} : {a['message']}"})
    for r in supplier_risk(ctx, as_of):
        if r["niveau"] in ("eleve", "critique"):
            out.append({"type": "risque", "gravite": "haute" if r["niveau"] == "critique" else "moyenne",
                        "lien": f"/fournisseurs/{r['supplier_id']}",
                        "message": f"Risque {r['niveau']} : {r['fournisseur']} — " + "; ".join(r["facteurs"][:2])})
    _ = (unallocated, PaymentAllocation)
    order = {"haute": 0, "moyenne": 1, "basse": 2}
    return sorted(out, key=lambda a: order[a["gravite"]])
