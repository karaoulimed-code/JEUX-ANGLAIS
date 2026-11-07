#!/usr/bin/env bash
# Restauration d'une sauvegarde dans une base VIDE (ne jamais restaurer par-dessus la production sans arrêt du service).
# Usage : AP_DB_URL=postgresql://ap:mdp@localhost/ap_restaure ./restauration.sh /srv/sauvegardes/ap-base-AAAAMMJJ-HHMMSS.dump [archive-pieces.tar.gz] [dossier-storage]
set -euo pipefail
DUMP="${1:?fichier .dump requis}"
: "${AP_DB_URL:?AP_DB_URL requis}"
DIR="$(dirname "$DUMP")"; STAMP="$(basename "$DUMP" .dump | sed 's/ap-base-//')"
if [ -f "$DIR/ap-$STAMP.sha256" ]; then ( cd "$DIR" && sha256sum -c "ap-$STAMP.sha256" ); fi
pg_restore --no-owner --clean --if-exists --dbname "$AP_DB_URL" "$DUMP"
if [ -n "${2:-}" ] && [ -n "${3:-}" ]; then mkdir -p "$3" && tar -xzf "$2" -C "$3"; fi
echo "Restauration terminée. Contrôlez l'intégrité : python manage.py verify-audit"
