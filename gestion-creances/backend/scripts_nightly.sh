#!/bin/sh
# Lance « python -m app.jobs nightly » une fois par jour à NIGHTLY_HOUR (3 h par défaut).
while true; do
  if [ "$(date +%H)" = "${NIGHTLY_HOUR:-03}" ]; then
    python -m app.jobs nightly || echo "Traitement nocturne : anomalie signalée $(date)"
    sleep 3700
  fi
  sleep 600
done
