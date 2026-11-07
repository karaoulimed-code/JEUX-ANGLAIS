"""Données de référence (paramétrage initial) — à exécuter une fois après la migration.

    python -m app.seed --admin-password 'MotDePasse!2026'

Les valeurs fiscales sont datées et marquées « à valider » : elles doivent être
confirmées par l'expert-comptable avant la mise en production (voir
docs/REGLEMENTATION.md).
"""
import argparse
import datetime as dt
import secrets
from decimal import Decimal

from sqlalchemy import select

from .db import SessionLocal
from .models import (Currency, DunningLevel, DunningTemplate, Parameter, PaymentMethod, ReferenceValue, TaxRate, User)
from .security import hash_password
from .services.params import DEFAULTS
from . import audit

START = dt.date(2020, 1, 1)
CHECKED = "Vérifié le 07/11/2026 sur sources publiques ; confirmer avec l'expert-comptable (LF 2026, loi n° 2025-17 du 12/12/2025)."

TAXES = [
    ("TVA19", "TVA 19 %", "TVA", Decimal("19"), None, False, "Taux général de TVA – Code de la TVA, art. 7. " + CHECKED, True),
    ("TVA13", "TVA 13 %", "TVA", Decimal("13"), None, False, "Taux réduit – liste des opérations visées au Code de la TVA. " + CHECKED, True),
    ("TVA7", "TVA 7 %", "TVA", Decimal("7"), None, False, "Taux réduit – liste des opérations visées au Code de la TVA. " + CHECKED, True),
    ("TVA0", "Exonéré / suspension de TVA", "TVA", Decimal("0"), None, False, "Opérations exonérées, en suspension ou à l'export : mention obligatoire sur la facture.", True),
    ("TIMBRE", "Droit de timbre sur facture", "TIMBRE", None, Decimal("1.000"), False,
     "Montant de 1,000 TND applicable depuis la LF 2022 ; la LF 2026 prévoyait une révision : MONTANT À CONFIRMER avant mise en production.", True),
    ("FODEC", "FODEC 1 %", "AUTRE", Decimal("1"), None, True,
     "Fonds de développement de la compétitivité (produits industriels), inclus dans l'assiette de TVA. Applicabilité à vérifier selon l'activité.", True),
]

METHODS = [
    ("ESP", "Espèces", "ESPECES", False), ("CHQ", "Chèque", "CHEQUE", True), ("VIR", "Virement bancaire", "VIREMENT", False),
    ("EFF", "Effet de commerce (traite)", "EFFET", True), ("RS", "Retenue à la source (certificat)", "RETENUE_SOURCE", False),
    ("AUTRE", "Autre moyen", "AUTRE", False),
]

TEMPLATES = [
    ("RAPPEL", "Rappel avant échéance", "EMAIL", "Rappel : échéance prochaine – {client}",
     "Madame, Monsieur,\n\nNous vous rappelons que les factures suivantes arrivent prochainement à échéance :\n{liste_factures}\n\n"
     "Montant total : {montant_du}.\n\nNous vous remercions de bien vouloir prévoir leur règlement.\n\nCordialement,\n{responsable}\n{societe}"),
    ("RELANCE1", "Première relance amiable", "LETTRE", "Relance – factures échues – {client}",
     "{contact},\n\nSauf erreur ou omission de notre part, les factures suivantes restent impayées à ce jour :\n{liste_factures}\n\n"
     "Soit un montant total de {montant_du}.\n\nIl s'agit peut-être d'un simple oubli : nous vous remercions de bien vouloir procéder "
     "à leur règlement dans les meilleurs délais. Si votre paiement a été effectué entre-temps, merci de ne pas tenir compte de ce courrier.\n\n"
     "Cordialement,\n{responsable}\n{societe}"),
    ("RELANCE2", "Deuxième relance", "LETTRE", "Deuxième relance – {client}",
     "{contact},\n\nMalgré notre précédent rappel, nous constatons que les factures suivantes demeurent impayées :\n{liste_factures}\n\n"
     "Montant total dû : {montant_du}.\n\nNous vous demandons de régulariser cette situation sous huit (8) jours. À défaut, nous serons "
     "contraints de suspendre nos livraisons et d'engager une procédure de recouvrement.\n\n{responsable}\n{societe}"),
    ("MED", "Mise en demeure", "LETTRE", "MISE EN DEMEURE – {client}",
     "Lettre recommandée avec accusé de réception\n\n{client}\n{adresse_client}\n\nObjet : mise en demeure de payer\n\n{contact},\n\n"
     "Malgré nos relances, vous restez redevable de la somme de {montant_du} au titre des factures suivantes :\n{liste_factures}\n\n"
     "Par la présente, nous vous mettons en demeure de régler cette somme dans un délai de quinze (15) jours à compter de la réception "
     "de ce courrier. À défaut, nous transmettrons le dossier à notre conseil afin d'engager toute procédure judiciaire utile, "
     "sans autre avis.\n\n{responsable}\n{societe}\n\n[Modèle à faire valider par votre avocat avant usage.]"),
    ("JURIDIQUE", "Transmission au service juridique", "EMAIL", "Transmission contentieux – {client} ({code_client})",
     "Dossier transmis au service juridique.\n\nClient : {client} ({code_client})\nMontant dû : {montant_du}\nRetard maximal : {jours_retard} jours\n\n"
     "Factures :\n{liste_factures}\n\nHistorique des relances disponible dans le logiciel.\n\n{responsable}"),
]
LEVELS = [(1, "RELANCE1", "Première relance amiable", 7, False), (2, "RELANCE2", "Deuxième relance", 30, False),
          (3, "MED", "Mise en demeure", 60, False), (4, "JURIDIQUE", "Transmission au service juridique", 90, True)]

GOVERNORATES = ["Tunis", "Ariana", "Ben Arous", "Manouba", "Nabeul", "Zaghouan", "Bizerte", "Béja", "Jendouba", "Le Kef", "Siliana",
                "Sousse", "Monastir", "Mahdia", "Sfax", "Kairouan", "Kasserine", "Sidi Bouzid", "Gabès", "Médenine", "Tataouine",
                "Gafsa", "Tozeur", "Kébili"]
CATEGORIES = [("PME", "PME"), ("GE", "Grande entreprise"), ("ADM", "Administration / établissement public"),
              ("PART", "Particulier"), ("EXPORT", "Client étranger"), ("REV", "Revendeur / distributeur")]
SECTORS = [("COMMERCE", "Commerce"), ("INDUSTRIE", "Industrie"), ("BTP", "Bâtiment et travaux publics"), ("SERVICES", "Services"),
           ("AGRO", "Agroalimentaire"), ("SANTE", "Santé"), ("TOURISME", "Tourisme / hôtellerie"), ("TIC", "Technologies"),
           ("TRANSPORT", "Transport et logistique"), ("PUBLIC", "Secteur public")]

PARAM_META = {
    "invoice.stamp_duty_code": ("Code de la taxe utilisée comme droit de timbre sur facture.", None, False),
    "provision.nct.grid": ("Grille indicative de taux de provision par ancienneté (politique interne). Les NCT n'imposent aucun taux : "
                           "la provision doit refléter la perte probable, appréciée dossier par dossier.", "NCT 01 – Norme générale (prudence).", True),
    "provision.nct.base": ("Base de provision NCT : HT (TVA récupérable en cas de perte définitive) ou TTC.", "À trancher avec l'expert-comptable selon les conditions de récupération de la TVA.", True),
    "provision.ifrs9.matrix": ("Matrice de pertes attendues IFRS 9 (approche simplifiée) en % par tranche d'ancienneté.", "IFRS 9 §5.5.15 et B5.5.35 ; à calibrer sur l'historique + informations prospectives.", True),
    "writeoff.recover_vat": ("Régularisation de la TVA collectée lors du passage en perte.", "Conditions du Code de la TVA à vérifier (jugement, procédure collective…).", True),
    "accounts": ("Plan de comptes utilisé pour les écritures proposées.", "Système comptable des entreprises (loi n° 96-112) : numéros à adapter au plan de comptes de l'entreprise.", True),
    "risk.weights": ("Pondérations de la notation de risque (total 100).", None, False),
    "dso.method": ("COMPTABLE (encours / CA TTC × jours) ou EPUISEMENT (count-back).", None, False),
}


def run(admin_password: str | None, admin_username: str = "admin") -> None:
    db = SessionLocal()
    try:
        if not db.execute(select(TaxRate)).first():
            for code, label, kind, rate, fixed, inbase, src, tv in TAXES:
                db.add(TaxRate(code=code, label=label, kind=kind, rate=rate, fixed_amount=fixed, in_vat_base=inbase, valid_from=START,
                               source=src, to_validate=tv, account_code=None))
        if not db.execute(select(PaymentMethod)).first():
            for code, label, kind, clr in METHODS:
                db.add(PaymentMethod(code=code, label=label, kind=kind, requires_clearing=clr))
        if not db.execute(select(Currency)).first():
            db.add_all([Currency(code="TND", label="Dinar tunisien", decimals=3), Currency(code="EUR", label="Euro", decimals=2),
                        Currency(code="USD", label="Dollar américain", decimals=2)])
        if not db.execute(select(DunningTemplate)).first():
            tpls = {}
            for code, label, ch, subj, body in TEMPLATES:
                t = DunningTemplate(code=code, label=label, channel=ch, subject=subj, body=body)
                db.add(t)
                tpls[code] = t
            db.flush()
            for lvl, code, label, days, legal in LEVELS:
                db.add(DunningLevel(level=lvl, code=code, label=label, days_after_due=days, template_id=tpls[code].id, escalate_to_legal=legal))
        if not db.execute(select(ReferenceValue)).first():
            for g in GOVERNORATES:
                db.add(ReferenceValue(kind="ZONE", code=g.upper().replace(" ", "_"), label=g))
            for c, l in CATEGORIES:
                db.add(ReferenceValue(kind="CATEGORY", code=c, label=l))
            for c, l in SECTORS:
                db.add(ReferenceValue(kind="SECTOR", code=c, label=l))
        if not db.execute(select(Parameter)).first():
            for k, v in DEFAULTS.items():
                desc, src, tv = PARAM_META.get(k, (None, None, False))
                db.add(Parameter(key=k, value=v, valid_from=START, description=desc, source=src, to_validate=tv))
        admin = db.execute(select(User).where(User.username == admin_username)).scalar_one_or_none()
        if not admin:
            pw = admin_password or secrets.token_urlsafe(12) + "A1"
            admin = User(username=admin_username, full_name="Administrateur", role="ADMIN", password_hash=hash_password(pw), must_change_password=True)
            db.add(admin)
            db.flush()
            audit.log(db, None, "SEED", "system", None, {"admin": admin_username})
            if not admin_password:
                print(f"Compte administrateur créé : {admin_username} / {pw}  (à changer à la première connexion)")
        db.commit()
        print("Paramétrage initial en place.")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-password")
    ap.add_argument("--admin-username", default="admin")
    a = ap.parse_args()
    run(a.admin_password, a.admin_username)
