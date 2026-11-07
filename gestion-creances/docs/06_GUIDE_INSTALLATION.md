---
title: "Guide d'installation, de déploiement et d'exploitation"
subtitle: "Gestion intégrée du poste clients — version 1.0"
---

# 1. Prérequis

| Mode | Prérequis |
|---|---|
| Production (recommandé) | Serveur Linux (2 vCPU, 4 Go de RAM, 40 Go de disque) avec Docker et Docker Compose ; nom de domaine et certificat HTTPS |
| Poste de développement | Python 3.12+, Node.js 20+, PostgreSQL 14+ |

# 2. Installation en production (Docker)

```bash
cd gestion-creances
cp .env.example .env                 # renseigner DB_PASSWORD, SECRET_KEY, PUBLIC_URL
docker compose up -d --build         # base, API, interface, sauvegardes, traitements nocturnes
docker compose exec backend python -m app.seed --admin-password 'MotDePasseFort2026'
```

L'application est accessible sur `http://serveur:8080` (port `HTTP_PORT`). Placer un reverse proxy HTTPS (Nginx, Caddy, Traefik) devant ce port. Première connexion : `admin`, changement de mot de passe imposé.

Ensuite, dans *Paramétrage* : renseigner la fiche société (`company`), faire valider les taux marqués « à valider », adapter le plan de comptes (`accounts`), créer les utilisateurs.

## Jeu de démonstration (uniquement sur une base de test)

```bash
docker compose exec backend python -m app.demo --yes
```

Il crée 10 clients fictifs préfixés **[DÉMO]** (indicateur `is_demo`), 14 mois de factures et de règlements passés par les mêmes services que la saisie réelle, et 4 comptes : `demo.daf`, `demo.compta`, `demo.recouv`, `demo.commercial` (mot de passe `Demo2026!x`). **Ne jamais l'exécuter sur la base de production.**

# 3. Installation pour le développement

```bash
# Base
sudo -u postgres psql -c "CREATE USER creances WITH PASSWORD 'creances' CREATEDB;"
sudo -u postgres createdb -O creances creances
sudo -u postgres createdb -O creances creances_test

# API
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env      # adapter GPC_DATABASE_URL
alembic upgrade head
python -m app.seed --admin-password 'Admin2026!x'
uvicorn app.main:app --reload --port 8000      # documentation : http://localhost:8000/api/docs

# Interface
cd ../frontend && npm install && npm run dev    # http://localhost:5173
```

Script SQL de création complet (sans Alembic) : `database/schema.sql`.

# 4. Tests automatisés

```bash
cd backend && . .venv/bin/activate && python -m pytest -q
```

38 tests sur une base PostgreSQL réelle (`creances_test`, recréée à chaque exécution) : calculs de facture (multi-taux, remise, FODEC, timbre), numérotation et intangibilité, règlements partiels, lettrage FIFO et avances, rejets de chèques, délettrage, avoirs, écarts de règlement, retenue à la source, devises et écarts de change, balance âgée (bornes, échéanciers, date passée, devise), DSO, taux de recouvrement, concentration, notation de risque, plafonds, provisions NCT et IFRS 9, séparation des fonctions, passage en perte, droits par rôle, verrouillage, sessions, journal d'audit, écritures, imports, tous les états dans tous les formats, prévisions, relances, et scénario mixte de concordance à plusieurs dates.

# 5. Sauvegarde et restauration

## Sauvegarde automatique

Le service `backup` réalise chaque jour à `BACKUP_HOUR` (2 h par défaut) :

- un export de la base (`creances-AAAAMMJJ-HHMMSS.dump`, format pg_dump personnalisé, compressé) ;
- une archive des pièces jointes (`pieces-….tar.gz`) ;
- un fichier d'empreintes SHA-256 (`sauvegarde-….sha256`) ;
- un contrôle de lisibilité de l'export ;
- la suppression des sauvegardes de plus de `BACKUP_RETENTION_DAYS` jours (30 par défaut).

Les fichiers sont dans `gestion-creances/backups/`. **Copier ce dossier chaque jour hors du serveur** (autre site, stockage chiffré) : une sauvegarde sur la même machine ne protège pas d'une panne de disque ou d'un rançongiciel.

## Sauvegarde manuelle (avant une mise à jour)

```bash
docker compose exec backup sh /scripts/backup.sh /backups /data/storage
```

## Restauration

```bash
docker compose stop backend scheduler
docker compose exec backup sh /scripts/restore.sh /backups/creances-AAAAMMJJ-HHMMSS.dump /backups/pieces-AAAAMMJJ-HHMMSS.tar.gz creances
docker compose start backend scheduler
```

Le script vérifie les empreintes, demande la confirmation `OUI`, recrée la base et restaure les pièces. Après restauration : *Journal d'audit › Vérifier l'intégrité* et *Intégration comptable › contrôle de concordance* doivent être au vert. Procédure testée le 07/11/2026 (restauration complète, chaîne d'audit et concordance vérifiées).

Recommandation : tester une restauration sur une base de test **chaque trimestre**.

# 6. Mise à jour du logiciel

```bash
docker compose exec backup sh /scripts/backup.sh /backups /data/storage   # 1. sauvegarde
git pull                                                                    # 2. nouvelle version
docker compose up -d --build                                                # 3. migrations appliquées au démarrage
```

# 7. Exploitation courante

| Tâche | Fréquence | Moyen |
|---|---|---|
| Notation du risque et contrôle de concordance | Chaque nuit (3 h) | Service `scheduler` (`python -m app.jobs nightly`), tracé dans le journal d'audit |
| Saisie des cours de change | À chaque facture ou règlement en devise | *Paramétrage › Devises et cours* (source BCT) |
| Validation et export des écritures | Hebdomadaire ou mensuelle | *Intégration comptable* |
| Campagne de provisions | Trimestrielle et à la clôture | *Créances douteuses et provisions* |
| Revue des habilitations | Trimestrielle | *Utilisateurs* |
| Vérification des sauvegardes hors site | Hebdomadaire | Administrateur |
| Mise à jour des paramètres fiscaux | À chaque loi de finances (janvier) | *Paramétrage*, avec date d'effet |

# 8. Variables de configuration (API)

| Variable | Rôle | Défaut |
|---|---|---|
| `GPC_DATABASE_URL` | Connexion PostgreSQL | — |
| `GPC_SECRET_KEY` | Clé de signature des jetons (longue, aléatoire, secrète) | à définir |
| `GPC_ACCESS_TOKEN_MINUTES` | Durée de vie du jeton | 30 |
| `GPC_SESSION_IDLE_MINUTES` | Déconnexion après inactivité | 30 |
| `GPC_MAX_FAILED_LOGINS` / `GPC_LOCKOUT_MINUTES` | Verrouillage | 5 / 15 |
| `GPC_STORAGE_DIR` | Stockage des pièces jointes | ./storage |
| `GPC_CORS_ORIGINS` | Origines autorisées de l'interface | http://localhost:5173 |
