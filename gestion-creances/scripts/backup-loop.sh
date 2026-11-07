#!/bin/sh
# Boucle du service « backup » : une sauvegarde par jour à BACKUP_HOUR,
# puis suppression des fichiers de sauvegarde plus anciens que RETENTION_DAYS.
set -u
while true; do
  if [ "$(date +%H)" = "${BACKUP_HOUR:-02}" ]; then
    sh /scripts/backup.sh /backups /data/storage || echo "ECHEC DE LA SAUVEGARDE $(date)"
    find /backups -maxdepth 1 -type f \( -name 'creances-*.dump' -o -name 'pieces-*.tar.gz' -o -name 'sauvegarde-*.sha256' \) \
      -mtime +"${RETENTION_DAYS:-30}" -exec rm -f {} \;
    sleep 3700
  fi
  sleep 600
done
