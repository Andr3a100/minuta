"""L'esempio della lezione 4: un paragrafo del fascicolo penale di Studio
Meridiana (inventato), passato dalla pseudonimizzazione del pilota.

    .venv/bin/python esempi/genera_04.py

Il fascicolo conosce l'indagato e la sua impresa, non il dipendente ferito.
La prova tests/test_esempi.py rifà l'uscita e la confronta con il file
stampato nel libro.
"""

from pathlib import Path

from minuta.leaks import fughe
from minuta.pseudonym import Pseudonimizzatore

CARTELLA = Path(__file__).resolve().parent
NOTI = {"Alessandro Riva": "PERSONA", "Logistica Riva S.r.l.": "SOGGETTO"}


def uscita() -> str:
    testo = (CARTELLA / "04-paragrafo.txt").read_text("utf-8")
    nascosto = Pseudonimizzatore(noti=dict(NOTI)).nascondi(testo)
    trovate = fughe(nascosto, set(NOTI))
    esito = "superato" if not trovate else f"bloccato: {trovate}"
    return f"{nascosto.rstrip()}\n\nControllo delle fughe: {esito}\n"


if __name__ == "__main__":
    (CARTELLA / "04-paragrafo-pseudonimizzato.txt").write_text(uscita(), "utf-8")
    print(uscita(), end="")
