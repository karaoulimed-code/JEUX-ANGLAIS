#!/bin/sh
# Restauration : ATTENTION, remplace intégralement la base cible.
# Usage : PGHOST=... PGUSER=... PGPASSWORD=... ./restore.sh creances-AAAAMMJJ-HHMMSS.dump [pieces-....tar.gz] [base_cible]
set -eu
DUMP=$1
PIECES=${2:-}
TARGET=${3:-creances}
DIR=$(dirname "$DUMP")
STAMP=$(basename "$DUMP" .dump | sed 's/^creances-//')
if [ -f "$DIR/sauvegarde-$STAMP.sha256" ]; then
  (cd "$DIR" && sha256sum -c "sauvegarde-$STAMP.sha256")
else
  echo "Avertissement : fichier d'empreintes absent, intégrité non vérifiée"
fi
echo "La base « $TARGET » va être remplacée par $DUMP. Taper OUI pour confirmer :"
read -r ok
[ "$ok" = "OUI" ] || { echo "Abandon."; exit 1; }
dropdb --if-exists "$TARGET"
createdb "$TARGET"
pg_restore --no-owner -d "$TARGET" "$DUMP"
if [ -n "$PIECES" ]; then
  mkdir -p "${STORAGE_DIR:-/data/storage}"
  tar -xzf "$PIECES" -C "${STORAGE_DIR:-/data/storage}"
fi
echo "Restauration terminée. Vérifier : Journal d'audit > Vérifier l'intégrité, puis Intégration comptable > contrôle de concordance."
