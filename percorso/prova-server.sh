#!/bin/bash
# Prova della Parte IV: i comandi sul server dello studio.
#
# Il server dello studio, nella prova, è la macchina Ubuntu della prova
# automatica, presa in prestito. Esegue in bash i comandi delle lezioni
# della Parte IV, come li scrive chi amministra il server, e ne scrive il
# verbale. Il libro stampa gli output presi da questo verbale.
#
#   bash percorso/prova-server.sh VERBALE
set -euo pipefail
if [ -z "${CI:-}" ]; then
    HOME="$(mktemp -d)"
    export HOME
fi
unset CI BUILD_NUMBER
umask 022

percorso="$(cd "$(dirname "$0")" && pwd)"
lab="$(cd "$percorso/.." && pwd)"
verbale="$1"

rm -rf ~/minuta ~/.materiale
mkdir -p ~/minuta ~/.materiale
git clone -q "$lab" ~/minuta/laboratorio
git -C ~/minuta/laboratorio switch -q -C main
for versione in $(cat "$percorso"/sessioni/server/*.txt |
    sed -n 's/^git switch --detach \(v[0-9.]*\)$/\1/p' | sort -u); do
    git -C ~/minuta/laboratorio rev-parse -q --verify \
        "refs/tags/$versione" >/dev/null ||
        git -C ~/minuta/laboratorio tag "$versione" HEAD
done
echo "passphrase di prova per sarti" >~/.materiale/sarti.txt

# L'insieme di addestramento lo prepara il computer dello studio (lezione
# 28) e arriva sul server: qui lo prepara la prova, con gli stessi comandi,
# in una copia a parte, e lo mette dove l'avrebbe copiato lo studio.
studio="$(mktemp -d)"
git clone -q "$lab" "$studio/laboratorio"
(
    cd "$studio/laboratorio"
    git switch -q -C main
    python3 -m venv .venv
    .venv/bin/python -m pip install -q -r requirements.txt
    .venv/bin/python strumenti/configura_locale.py
    .venv/bin/python -m app.manage migra
    .venv/bin/python -m app.manage crea-utente sarti --ruolo avvocato \
        --nome "Elena Sarti" --passphrase-stdin <~/.materiale/sarti.txt
    .venv/bin/python -m app.manage carica-archivio archivio/pdf --da sarti
    .venv/bin/python -m app.manage addestramento --da sarti
) >/dev/null
mkdir -p ~/minuta/laboratorio/dati/addestramento
cp "$studio/laboratorio/dati/addestramento/sarti.jsonl" \
    ~/minuta/laboratorio/dati/addestramento/

export COLUMNS=79 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_COLOR=1
# Il server non chiama nessun modello in cloud.
unset OPENAI_API_KEY MINUTA_API_KEY ANTHROPIC_API_KEY
# shellcheck disable=SC2016
ps0_bash='$(history 1 | sed "s/^ *[0-9]* *//")\n'

sessione() {
    local file="$percorso/sessioni/server/$1.txt"
    echo "=== sessione $1 · server"
    (cd ~ && env PS1='\W \$ ' PS0="$ps0_bash" HISTFILE=/dev/null \
        HF_HUB_DISABLE_PROGRESS_BARS=1 TRANSFORMERS_VERBOSITY=error \
        TOKENIZERS_PARALLELISM=false \
        bash --norc --noprofile --noediting -i <"$file" 2>&1)
    echo
}

{
    echo "== Sistema"
    uname -srm
    date -u +"%Y-%m-%dT%H:%M:%SZ"
    echo
    # Lezione 30: dove gira Minuta, e l'addestramento in locale.
    sessione l30
    echo "== Fine"
} >"$verbale"
cp ~/minuta/laboratorio/addestramento.json "$(dirname "$verbale")/" || true
