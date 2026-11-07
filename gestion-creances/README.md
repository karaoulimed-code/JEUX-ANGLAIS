# Gestion intégrée du poste clients

Logiciel professionnel de gestion des créances clients (*Accounts Receivable Management*) pour PME tunisiennes : clients, factures et échéances, encaissements et lettrage, balance âgée, recouvrement, risque, provisions (NCT / IFRS 9), tableau de bord, états et intégration comptable — sur **une seule base de données** et un cycle financier unique.

## Démarrage rapide (Docker)

```bash
cp .env.example .env            # renseigner DB_PASSWORD et SECRET_KEY
docker compose up -d --build
docker compose exec backend python -m app.seed --admin-password 'MotDePasseFort2026'
# interface : http://localhost:8080 — API : http://localhost:8080/api/docs
```

Données de démonstration (base de test uniquement) : `docker compose exec backend python -m app.demo --yes`.

## Contenu

| Dossier | Contenu |
|---|---|
| `backend/` | API FastAPI, règles métier (`app/services`), migrations Alembic, tests (`pytest`) |
| `frontend/` | Interface React / TypeScript (Mantine) |
| `database/schema.sql` | Script SQL complet de création de la base (tables, contraintes, déclencheurs) |
| `scripts/` | Sauvegarde, restauration, boucle de sauvegarde quotidienne |
| `docs/` | Cahier des charges, modèle de données, architecture et sécurité, indicateurs, réglementation, guides d'installation et d'utilisation, plan de développement (Markdown et Word) |

## Tests

```bash
cd backend && . .venv/bin/activate && python -m pytest -q     # 38 tests, base PostgreSQL réelle
```

## Avertissement

Les taux et règles fiscales tunisiennes sont paramétrés, datés et marqués « à valider » : ils doivent être confirmés par un expert-comptable avant la mise en production (voir `docs/05_REGLEMENTATION.md`).
