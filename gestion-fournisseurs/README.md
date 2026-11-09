# Gestion des dettes fournisseurs (Accounts Payable) — PME tunisiennes

Logiciel intégré de gestion du poste fournisseurs : **demande d'achat → commande → réception → facture → contrôle à trois niveaux → validation → échéance → préparation et autorisation du paiement → décaissement → rapprochement bancaire → comptabilité → reporting et prévisions de trésorerie**.

Conforme au Système comptable des entreprises tunisien (loi n° 96-112), paramétrable (TVA, retenue à la source, timbre, plan de comptes, seuils) sans modification du code, et aligné sur les bonnes pratiques IFRS pour l'information de gestion.

## Essai immédiat (un double-clic, seul Python 3 est requis)

- **Windows** : double-cliquer sur `demarrer-demo.bat`
- **Mac / Linux** : lancer `./demarrer-demo.sh`

Le navigateur s'ouvre sur http://localhost:8000 — connexion `daf@demo.tn` / `Demo2026pass`. Base locale de démonstration (SQLite) ; pour un usage réel, suivre le guide d'installation (PostgreSQL).

## Démarrage avec Docker (démonstration)

```bash
cp deploy/env.exemple .env   # renseigner POSTGRES_PASSWORD et AP_SECRET_KEY
docker compose up -d --build
docker compose exec app python manage.py demo
```

Ouvrir http://localhost:8000 — comptes de démonstration `daf@demo.tn`, `compta@demo.tn`, `agent@demo.tn`, `tresor@demo.tn`, `dg@demo.tn`, `achats@demo.tn`, `lecture@demo.tn`, `admin@demo.tn` ; mot de passe `Demo2026pass`.
**Les données de démonstration sont fictives** (entreprise « SOCIÉTÉ DÉMO SARL — données fictives », bandeau « Démonstration »).

Installation sans Docker, production, HTTPS, sauvegardes : [`docs/06-guide-installation.md`](docs/06-guide-installation.md).

## Documentation

| Document | Contenu |
|---|---|
| [01 Cahier des charges](docs/01-cahier-des-charges.md) | Objectifs, périmètre, profils, processus, règles de gestion, cas particuliers, scénarios, hypothèses |
| [02 Conception technique](docs/02-conception-technique.md) | Architecture, choix techniques, sécurité, IA, SaaS, plan de tests |
| [03 Schéma de base](docs/03-schema-base-de-donnees.md) | 33 tables, relations (généré depuis le code) |
| [04 Plan de développement](docs/04-plan-developpement.md) | État d'avancement, feuille de route, limites connues |
| [05 Indicateurs](docs/05-indicateurs.md) | Formules et conventions (DPO, balance âgée, prévisions, risques) |
| [06 Installation](docs/06-guide-installation.md) | Déploiement, variables, sauvegarde, restauration |
| [07 Guide utilisateur](docs/07-guide-utilisateur.md) | Mode opératoire par profil |
| [08 Référentiel réglementaire](docs/08-referentiel-reglementaire.md) | Tunisie / IFRS, taux datés et sources, points à confirmer |
| [09 Référence API](docs/09-reference-api.md) | 104 opérations (documentation interactive : `/api/docs`) |

## Structure

```
backend/   FastAPI · SQLAlchemy · Alembic · pytest (54 tests)
frontend/  React · TypeScript · Vite · Recharts
docs/      dossier fonctionnel et technique
scripts/   sauvegarde.sh · restauration.sh
```

## Avertissement

Les taux fiscaux livrés ont été relevés le 07/11/2026 à partir de sources secondaires et sont marqués « à vérifier » dans l'application. Ils doivent être confirmés par l'expert-comptable de l'entreprise avant toute utilisation en production.
