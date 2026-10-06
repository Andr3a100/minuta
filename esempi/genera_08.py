"""L'esempio della lezione 8: la parte della riga del registro che il pilota
scriverebbe se mandasse al modello il paragrafo della lezione 4.

    .venv/bin/python esempi/genera_08.py

L'impronta, la lunghezza e l'esito del controllo delle fughe sono calcolati
con le funzioni del pilota, come in draft.prepara; la data, il modello, i
token e il costo li riempie la chiamata, che qui non si fa. La prova
tests/test_esempi.py rifà l'uscita e la confronta con il file stampato nel
libro.
"""

import hashlib
from pathlib import Path

from minuta.leaks import fughe
from minuta.pseudonym import Pseudonimizzatore

CARTELLA = Path(__file__).resolve().parent
NOTI = {"Alessandro Riva": "PERSONA", "Logistica Riva S.r.l.": "SOGGETTO"}


def uscita() -> str:
    testo = (CARTELLA / "04-paragrafo.txt").read_text("utf-8")
    inviato = Pseudonimizzatore(noti=dict(NOTI)).nascondi(testo)
    trovate = fughe(inviato, set(NOTI))
    esito = "superato" if not trovate else f"bloccato: {trovate}"
    # L'impronta va a capo da sola: la riga resta entro le 79 colonne.
    return (
        "{\n"
        '  "inviato_sha256":\n'
        f'    "{hashlib.sha256(inviato.encode()).hexdigest()}",\n'
        f'  "caratteri_inviati": {len(inviato)},\n'
        f'  "controllo_fughe": "{esito}"\n'
        "}\n"
    )


if __name__ == "__main__":
    (CARTELLA / "08-registro-del-paragrafo.json").write_text(uscita(), "utf-8")
    print(uscita(), end="")
