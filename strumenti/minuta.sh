#!/bin/bash
# Un comando di Minuta per le attività pianificate (lezione 33): parte dalla
# cartella del laboratorio, con l'ambiente di Minuta, e aggiunge l'uscita
# al file del mese in log/, con la data e il comando.
#
#   strumenti/minuta.sh copia
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
mkdir -p log
{
    date -u +"== %Y-%m-%dT%H:%M:%SZ · $*"
    .venv/bin/python -m app.manage "$@"
    echo "== uscita $?"
} >>"log/minuta-$(date -u +%Y-%m).txt" 2>&1
