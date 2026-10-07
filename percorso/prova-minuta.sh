#!/bin/bash
# Prova della Parte III su macOS e Linux: i comandi del lettore.
#
# Esegue, come li scrive il lettore, il primo avvio di Minuta (lezione 15)
# in una shell interattiva (zsh su macOS, bash su Linux), e ne scrive il
# verbale. Il libro stampa gli output presi da questo verbale.
#
#   bash percorso/prova-minuta.sh VERBALE zsh|bash
#
# Nella CI lavora nella cartella personale della macchina di prova; altrove
# in una cartella personale temporanea, e non tocca niente di chi lo lancia.
# Il laboratorio è quello dell'ultimo commit, come lo trova chi lo scarica.
set -euo pipefail
if [ -z "${CI:-}" ]; then
    HOME="$(mktemp -d)"
    export HOME
fi
# Le sessioni girano senza le variabili con cui la CI si annuncia: pytest,
# quando le trova, non accorcia i messaggi, e sul computer del lettore li
# accorcia.
unset CI BUILD_NUMBER
umask 022

percorso="$(cd "$(dirname "$0")" && pwd)"
lab="$(cd "$percorso/.." && pwd)"
verbale="$1"
shell_lettore="${2:-bash}"

# Il punto di partenza della lezione 15: la cartella minuta della Parte 0,
# con dentro il laboratorio, un repository Git con un'etichetta per ogni
# versione di Minuta. Ogni lezione passa alla sua versione con git switch;
# quella a cui si sta ancora lavorando prende l'etichetta dall'ultimo
# commit. Le passphrase di prova stanno in file a parte.
rm -rf ~/minuta/laboratorio ~/.materiale
mkdir -p ~/minuta ~/.materiale
git clone -q "$lab" ~/minuta/laboratorio
for versione in $(cat "$percorso"/sessioni/unix/*.txt |
    sed -n 's/^git switch --detach \(v[0-9.]*\)$/\1/p' | sort -u); do
    git -C ~/minuta/laboratorio rev-parse -q --verify \
        "refs/tags/$versione" >/dev/null ||
        git -C ~/minuta/laboratorio tag "$versione" HEAD
done
for nome in sarti dini righi valli irene rosa; do
    echo "passphrase di prova per $nome" >~/.materiale/"$nome".txt
done
echo "corta" >~/.materiale/corta.txt

# curl mostra la barra di avanzamento solo quando l'output non va sullo
# schermo: qui la si toglie, per avere lo stesso output del lettore.
CURL_HOME="$(mktemp -d)"
export CURL_HOME
echo "--no-progress-meter" >"$CURL_HOME/.curlrc"

# Gli output larghi al massimo 79 colonne, come il codice del libro.
export COLUMNS=79
# La prova non usa mai una chiave vera.
unset OPENAI_API_KEY MINUTA_API_KEY ANTHROPIC_API_KEY

zdotdir="$(mktemp -d)"
cat >"$zdotdir/.zshrc" <<'ZSHRC'
PS1='%1~ %# '
umask 022
unsetopt PROMPT_SP PROMPT_CR
preexec() { print -r -- "$1"; }
ZSHRC
# shellcheck disable=SC2016
ps0_bash='$(history 1 | sed "s/^ *[0-9]* *//")\n'

sessione() {
    local file="$percorso/sessioni/unix/$1.txt"
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

    sessione l15

    # Lezione 15: Minuta gira in un secondo terminale.
    registro="$(mktemp)"
    (cd ~/minuta/laboratorio && exec .venv/bin/python -m uvicorn \
        app.main:app --host 127.0.0.1 --port 8000) >"$registro" 2>&1 &
    server=$!
    for _ in $(seq 1 100); do
        curl -s -o /dev/null http://127.0.0.1:8000/salute && break
        sleep 0.2
    done
    sessione l15b
    kill "$server"
    wait "$server" 2>/dev/null || true
    echo "### [esito:l15b-server]"
    cat "$registro"
    echo "### [/esito:l15b-server]"
    echo
    echo "== Fine"
} >"$verbale"
