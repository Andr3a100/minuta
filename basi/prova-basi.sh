#!/bin/bash
# Prova della Parte 0 su macOS e Linux: le lezioni B2-B8 di Minuta.
#
# Esegue i comandi delle lezioni B2-B8 così come li scrive il lettore, in
# una shell interattiva (zsh su macOS, bash su Linux), e ne scrive il
# verbale. Il libro stampa gli output presi da questo verbale.
#
#   bash basi/prova-basi.sh VERBALE zsh|bash
#
# Nella CI lavora nella cartella personale della macchina di prova; altrove
# in una cartella personale temporanea, e non tocca niente di chi lo lancia.
set -euo pipefail
if [ -z "${CI:-}" ]; then
    HOME="$(mktemp -d)"
    export HOME
fi
# Le sessioni girano senza le variabili con cui la CI si annuncia: pytest,
# quando le trova, non accorcia i messaggi, e sul computer del lettore li
# accorcia.
unset CI BUILD_NUMBER
# I permessi dei file nuovi come su un computer qualsiasi.
umask 022

basi="$(cd "$(dirname "$0")" && pwd)"
verbale="$1"
shell_lettore="${2:-bash}"

# Il punto di partenza della lezione B2: la cartella creata nella lezione
# B1 con il Finder o con Esplora file, con dentro il file LEGGIMI.md.
rm -rf ~/minuta ~/.materiale
mkdir -p ~/minuta/quaderno ~/.materiale
cp "$basi/LEGGIMI.md" ~/minuta/quaderno/
cp -R "$basi/conti" "$basi/sql" "$basi/documenti" ~/.materiale/

# curl mostra la barra di avanzamento solo quando l'output non va sullo
# schermo: qui la si toglie, per avere lo stesso output del lettore.
CURL_HOME="$(mktemp -d)"
export CURL_HOME
echo "--no-progress-meter" >"$CURL_HOME/.curlrc"

# Gli output larghi al massimo 79 colonne, come il codice del libro.
export COLUMNS=79

# Git parte senza la configurazione personale della macchina di prova,
# come su un computer dove non è mai stato configurato.
GIT_CONFIG_GLOBAL="$(mktemp -d)/gitconfig"
export GIT_CONFIG_GLOBAL

# La configurazione della shell di prova: un prompt come quello di macOS
# e la riga di comando ripetuta dopo il prompt, come la vedrebbe chi la
# scrive: in zsh la stampa preexec, in bash PS0.
zdotdir="$(mktemp -d)"
cat >"$zdotdir/.zshrc" <<'ZSHRC'
PS1='%1~ %# '
umask 022
unsetopt PROMPT_SP PROMPT_CR
preexec() { print -r -- "$1"; }
ZSHRC
# PS0 si espande dopo la lettura della riga: history 1 è proprio quella.
# shellcheck disable=SC2016
ps0_bash='$(history 1 | sed "s/^ *[0-9]* *//")\n'

# Una sessione del lettore: i comandi arrivano alla shell uno alla volta,
# dalla cartella personale, e il verbale li riporta dopo il prompt,
# seguiti dal loro output.
sessione() {
    local file="$basi/sessioni/unix/$1.txt"
    echo "=== sessione $1 · $shell_lettore"
    case "$shell_lettore" in
        zsh)
            (cd ~ && ZDOTDIR="$zdotdir" zsh -i -s <"$file" 2>&1)
            ;;
        bash)
            (cd ~ && env PS1='\W \$ ' PS0="$ps0_bash" HISTFILE=/dev/null \
                bash --norc --noprofile --noediting -i <"$file" 2>&1)
            ;;
    esac
    echo
}

{
    echo "== Sistema"
    uname -srm
    date -u +"%Y-%m-%dT%H:%M:%SZ"
    echo

    sessione b2
    sessione b3
    sessione b4
    sessione b5

    # Lezione B6: il server gira in un secondo terminale, nella cartella
    # del quaderno. Il suo registro chiude la sessione.
    registro="$(mktemp)"
    (cd ~/minuta/quaderno &&
        PYTHONUNBUFFERED=1 exec python3 -m http.server 8000 \
            --bind 127.0.0.1) >"$registro" 2>&1 &
    server=$!
    for _ in $(seq 1 50); do
        curl -s -o /dev/null http://127.0.0.1:8000/ && break
        sleep 0.2
    done
    sessione b6
    kill "$server"
    wait "$server" 2>/dev/null || true
    echo "### [esito:b6-server]"
    grep -v '"GET / HTTP' "$registro" || true
    echo "### [/esito:b6-server]"
    echo


    sessione b7
    sessione b8
    echo "== Fine"
} >"$verbale"
