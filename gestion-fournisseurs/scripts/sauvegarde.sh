#!/usr/bin/env bash
# Sauvegarde complète : base PostgreSQL (format custom) + pièces justificatives.
# Usage : AP_DB_URL=postgresql://ap:motdepasse@localhost/ap AP_STORAGE_DIR=/chemin/storage ./sauvegarde.sh [/dossier/sauvegardes]
# Planification quotidienne (cron) : 30 1 * * * /opt/ap/scripts/sauvegarde.sh /srv/sauvegardes >> /var/log/ap-sauvegarde.log 2>&1
set -euo pipefail
DEST="${1:-./backups}"
RETENTION_JOURS="${AP_RETENTION_JOURS:-30}"
: "${AP_DB_URL:?AP_DB_URL requis (ex. postgresql://ap:mdp@localhost/ap)}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
pg_dump --format=custom --no-owner --file "$DEST/ap-base-$STAMP.dump" "$AP_DB_URL"
if [ -n "${AP_STORAGE_DIR:-}" ] && [ -d "$AP_STORAGE_DIR" ]; then
  tar -czf "$DEST/ap-pieces-$STAMP.tar.gz" -C "$AP_STORAGE_DIR" .
fi
( cd "$DEST" && sha256sum ap-*-"$STAMP".* > "ap-$STAMP.sha256" )
find "$DEST" -name 'ap-*' -mtime +"$RETENTION_JOURS" -delete
echo "Sauvegarde $STAMP terminée dans $DEST"
