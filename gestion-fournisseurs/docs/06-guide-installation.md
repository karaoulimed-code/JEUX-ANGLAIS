# Guide d'installation, d'exploitation et de déploiement

## Option A — Docker (recommandée, serveur ou poste dédié)

Prérequis : Docker et Docker Compose.

```bash
cd gestion-fournisseurs
cp deploy/env.exemple .env           # puis remplacer les deux secrets
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # pour générer chaque secret
docker compose up -d --build         # crée la base, applique les migrations, démarre l'application
docker compose exec app python manage.py init-company --name "Ma PME SARL" \
  --tax-id "1234567/A/M/000" --admin-email admin@mapme.tn --admin-password "MotDePasse2026"
```

Application : `http://serveur:8000` — API documentée : `http://serveur:8000/api/docs`.

Données de démonstration (environnement de test uniquement) : `docker compose exec app python manage.py demo`.

## Option B — Installation directe (Linux ou Windows)

Prérequis : Python 3.12+, Node.js 20+, PostgreSQL 14+.

```bash
# Base de données
sudo -u postgres psql -c "CREATE USER ap WITH PASSWORD 'mot-de-passe-fort';"
sudo -u postgres psql -c "CREATE DATABASE ap OWNER ap;"

# Application
cd gestion-fournisseurs/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export AP_DATABASE_URL="postgresql+psycopg://ap:mot-de-passe-fort@localhost/ap"
export AP_SECRET_KEY="<secret aléatoire de 48 caractères>"
python manage.py migrate
python manage.py init-company --name "Ma PME SARL" --admin-email admin@mapme.tn --admin-password "MotDePasse2026"

# Interface web
cd ../frontend && npm ci && npm run build

# Démarrage (sert l'API et l'interface)
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Développement : `uvicorn app.main:app --reload` et, dans `frontend`, `npm run dev` (http://localhost:5173, proxy vers l'API).

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `AP_DATABASE_URL` | Connexion PostgreSQL | SQLite local (test uniquement) |
| `AP_SECRET_KEY` | Signature des sessions — **obligatoire en production** | Clé éphémère (sessions perdues au redémarrage) |
| `AP_TOKEN_MINUTES` | Durée maximale d'une session | 480 |
| `AP_IDLE_MINUTES` | Fermeture après inactivité | 30 |
| `AP_MAX_FAILED_LOGINS` | Échecs avant verrouillage (15 min) | 5 |
| `AP_STORAGE_DIR` | Stockage des pièces justificatives | `backend/storage` |
| `AP_MAX_UPLOAD_MB` | Taille maximale d'une pièce | 15 |
| `AP_CORS_ORIGINS` | Origines autorisées (si l'interface est servie ailleurs) | `http://localhost:5173` |

## HTTPS (obligatoire hors réseau local)

Placer l'application derrière un reverse proxy. Exemple Caddy (certificat automatique) :

```
ap.mapme.tn {
    reverse_proxy 127.0.0.1:8000
}
```

## Mise à jour

```bash
git pull
docker compose up -d --build          # les migrations s'appliquent au démarrage
# ou, sans Docker : pip install -r requirements.txt && python manage.py migrate && npm run build
```

Toujours **sauvegarder avant** une mise à jour.

## Sauvegarde et restauration

Sauvegarde (base + pièces + empreintes SHA-256, rotation 30 jours) :

```bash
AP_DB_URL=postgresql://ap:mdp@localhost/ap AP_STORAGE_DIR=/srv/ap/storage \
  scripts/sauvegarde.sh /srv/sauvegardes
```

Planification quotidienne (crontab) :

```
30 1 * * * AP_DB_URL=postgresql://ap:mdp@localhost/ap AP_STORAGE_DIR=/srv/ap/storage /opt/ap/scripts/sauvegarde.sh /srv/sauvegardes >> /var/log/ap-sauvegarde.log 2>&1
```

Recommandations : copier chaque nuit le dossier de sauvegarde hors du serveur (disque externe chiffré ou stockage distant) ; tester une restauration chaque trimestre ; conserver au moins une sauvegarde annuelle pendant 10 ans (obligation de conservation).

Restauration (dans une base vide, service arrêté) :

```bash
AP_DB_URL=postgresql://ap:mdp@localhost/ap_restaure \
  scripts/restauration.sh /srv/sauvegardes/ap-base-AAAAMMJJ-HHMMSS.dump \
  /srv/sauvegardes/ap-pieces-AAAAMMJJ-HHMMSS.tar.gz /srv/ap/storage
AP_DATABASE_URL=postgresql+psycopg://ap:mdp@localhost/ap_restaure python manage.py verify-audit
```

Avec Docker : `docker compose exec db pg_dump -U ap -Fc ap > ap.dump`.

## Contrôles d'exploitation

| Fréquence | Contrôle |
|---|---|
| Quotidien | Journal de sauvegarde ; alertes du tableau de bord |
| Mensuel | Rapprochement auxiliaire / général ; contrôle d'intégrité du journal d'audit (écran Audit) ; revue des comptes utilisateurs |
| Trimestriel | Test de restauration ; revue des taux fiscaux et des seuils |

## Tests automatisés

```bash
cd backend && pytest                       # base SQLite en mémoire
AP_TEST_DATABASE_URL=postgresql+psycopg://ap:mdp@localhost/ap_test pytest   # PostgreSQL
```
