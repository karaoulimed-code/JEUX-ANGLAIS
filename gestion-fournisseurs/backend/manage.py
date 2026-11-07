"""Commandes d'administration.

  python manage.py migrate                         # crée / met à jour le schéma (Alembic)
  python manage.py init-company --name "Ma PME SARL" --tax-id 1234567/A/M/000 \
         --admin-email admin@mapme.tn --admin-password "MotDePasse2026"
  python manage.py demo                            # charge l'entreprise de DÉMONSTRATION (données fictives)
  python manage.py verify-audit                    # contrôle l'intégrité du journal d'audit chaîné
"""
import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.db import SessionLocal
from app.security import check_password_policy

HERE = Path(__file__).parent


def migrate():
    cfg = Config(str(HERE / "alembic.ini"))
    cfg.set_main_option("script_location", str(HERE / "migrations"))
    command.upgrade(cfg, "head")
    print("Schéma à jour.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Administration — Gestion des dettes fournisseurs")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    ic = sub.add_parser("init-company")
    ic.add_argument("--name", required=True)
    ic.add_argument("--tax-id")
    ic.add_argument("--admin-email", required=True)
    ic.add_argument("--admin-password", required=True)
    ic.add_argument("--admin-name", default="Administrateur")
    sub.add_parser("demo")
    sub.add_parser("verify-audit")
    a = p.parse_args(argv)

    if a.cmd == "migrate":
        migrate()
        return
    db = SessionLocal()
    try:
        if a.cmd == "init-company":
            from app.seed import create_company
            check_password_policy(a.admin_password)
            c, u = create_company(db, a.name, a.tax_id, a.admin_email, a.admin_password, a.admin_name)
            db.commit()
            print(f"Entreprise #{c.id} créée ; administrateur : {u.email}. Paramètres fiscaux chargés (à vérifier).")
        elif a.cmd == "demo":
            from app.seed import DEMO_PASSWORD, DEMO_USERS, load_demo
            c = load_demo(db)
            db.commit()
            print(f"Entreprise de démonstration : {c.name}")
            print("Comptes (mot de passe commun : " + DEMO_PASSWORD + ") :")
            for email, name, role in DEMO_USERS:
                print(f"  {email:22s} {role:13s} {name}")
        elif a.cmd == "verify-audit":
            from app.services.common import verify_audit_chain
            res = verify_audit_chain(db)
            print(res)
            sys.exit(0 if res["integre"] else 2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
