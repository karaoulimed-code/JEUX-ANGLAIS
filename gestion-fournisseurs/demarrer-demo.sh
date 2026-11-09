#!/usr/bin/env bash
# Démarrage de la démonstration (Mac / Linux) — base locale SQLite, aucune autre installation que Python 3.
set -e
cd "$(dirname "$0")/backend"
command -v python3 >/dev/null || { echo "Installez Python 3 : https://www.python.org/downloads/"; exit 1; }
[ -d .venv ] || { echo "Première installation (quelques minutes)…"; python3 -m venv .venv; }
. .venv/bin/activate
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
[ -f .secret_key ] || python -c "import secrets;print(secrets.token_urlsafe(48))" > .secret_key
export AP_SECRET_KEY="$(cat .secret_key)"
python manage.py migrate
python manage.py demo
echo "Logiciel démarré : http://localhost:8000 — connexion daf@demo.tn / Demo2026pass (Ctrl+C pour arrêter)"
( sleep 3; (open http://localhost:8000 || xdg-open http://localhost:8000) >/dev/null 2>&1 ) &
python -m uvicorn app.main:app --port 8000
