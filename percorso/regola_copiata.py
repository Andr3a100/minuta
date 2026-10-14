"""Lezione 40, errore deliberato: la regola del termine copiata.

    python percorso/regola_copiata.py

Il tipo nuovo vuole la sua regola del termine. La strada più corta è
copiare quella dell'opposizione al decreto (lezione 19) e cambiare nome,
giorni e norma. Lo script la copia così, in memoria, senza scriverla nei
file di config, e calcola la stessa scadenza con la regola copiata e con
quella scritta leggendo le norme.
"""

from __future__ import annotations

import sys
import textwrap
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minuta.scadenze import calcola, carica_regole, in_lettere  # noqa: E402

PARTENZA = date(2027, 7, 20)  # la notificazione del precetto di prova


def esito(nome: str, regole: dict) -> str:
    calcolo = calcola(nome, PARTENZA, regole)
    if calcolo.scadenza is None:
        return f"decide l'avvocato: {calcolo.da_decidere}"
    return in_lettere(calcolo.scadenza)


def main() -> None:
    regole = carica_regole()
    decreto = next(
        r
        for r in regole["termini"]
        if r["nome"].startswith("opposizione al d")
    )
    # [libro:copiata]
    copiata = {
        **decreto,
        "nome": "opposizione agli atti, copiata",
        "giorni": 20,
        "norma": "art. 617, primo comma, c.p.c.",
    }
    # [/libro:copiata]
    regole["termini"].append(copiata)
    print(f"Notificazione del precetto: {in_lettere(PARTENZA)}.")
    print(f"Con la regola copiata: {esito(copiata['nome'], regole)}.")
    letta = esito("opposizione agli atti esecutivi", regole)
    print(
        textwrap.fill(
            f"Con la regola letta: {letta}.", 79, subsequent_indent="  "
        )
    )
    senza = {
        **copiata,
        "nome": "senza sospensione",
        "sospensione_feriale": "no",
    }
    regole["termini"].append(senza)
    print(f"Se la sospensione non vale: {esito(senza['nome'], regole)}.")


if __name__ == "__main__":
    main()
