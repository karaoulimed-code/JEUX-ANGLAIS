#!/bin/sh
# Sauvegarde ponctuelle : base (pg_dump format personnalisé) + pièces jointes, avec empreintes SHA-256.
# Usage : PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=creances ./backup.sh [dossier_dest] [dossier_pieces]
set -eu
DEST=${1:-/backups}
STORAGE=${2:-/data/storage}
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"
pg_dump -Fc -Z 9 -f "$DEST/creances-$TS.dump"
FILES="creances-$TS.dump"
if [ -d "$STORAGE" ]; then
  tar -czf "$DEST/pieces-$TS.tar.gz" -C "$STORAGE" .
  FILES="$FILES pieces-$TS.tar.gz"
fi
( cd "$DEST" && sha256sum $FILES > "sauvegarde-$TS.sha256" )
# Contrôle immédiat : l'archive doit être lisible par pg_restore
pg_restore -l "$DEST/creances-$TS.dump" > /dev/null
echo "Sauvegarde OK : $DEST/creances-$TS.dump"
