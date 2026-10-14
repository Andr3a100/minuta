"""Lezione 34, errore deliberato: cambiare l'informativa senza consegnarla
di nuovo.

    python percorso/informativa_cambiata.py 2026-071

Lo studio attiva la regione europea del fornitore (lezione 6) e Rosa
aggiorna la frase dell'informativa sui trasferimenti. Nessuno la manda ai
clienti che avevano ricevuto quella di prima. Lo script scrive il testo
cambiato in una cartella temporanea, che poi cancella, e prova una
richiesta per il fascicolo prima e dopo il cambio. Il testo dello studio,
docs/informativa.md, non viene toccato.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import informativa  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.db import Fascicolo, make_engine, make_session_factory  # noqa: E402
from app.informativa import (  # noqa: E402
    InformativaMancante,
    ModelloConInformativa,
    ModelloDelFascicolo,
)
from minuta.model import ModelloFinto  # noqa: E402

# [libro:il-cambio]
PRIMA = (
    "I dati possono essere trattati\n"
    "fuori dallo Spazio economico europeo, con le clausole contrattuali "
    "tipo o\nuna decisione di adeguatezza."
)
DOPO = (
    "I dati restano nello Spazio\n"
    "economico europeo e in Svizzera, la regione europea del fornitore."
)
# [/libro:il-cambio]


def prova(settings, fascicolo_id: int) -> str:
    davanti = ModelloConInformativa(ModelloFinto(), settings.database_url)
    try:
        ModelloDelFascicolo(davanti, fascicolo_id).scrivi("Prova.", "Prova.")
    except InformativaMancante as exc:
        return f"non parte. {exc}"
    return "parte."


def stampa(inizio: str, settings, fascicolo_id: int) -> None:
    testo = f"{inizio} {prova(settings, fascicolo_id)}"
    print(textwrap.fill(testo, 79, subsequent_indent="  "))


def main(codice: str) -> None:
    settings = load_settings()
    engine = make_engine(settings.database_url)
    with make_session_factory(engine)() as db:
        fascicolo = db.scalar(
            select(Fascicolo).where(Fascicolo.codice == codice)
        )
        fascicolo_id = fascicolo.id
    engine.dispose()
    stampa(
        f"Con l'informativa di oggi, la richiesta per {codice}",
        settings,
        fascicolo_id,
    )
    testo = informativa.TESTO.read_text("utf-8").replace("\r\n", "\n")
    if PRIMA not in testo:
        raise SystemExit("La frase sui trasferimenti non è quella attesa.")
    with tempfile.TemporaryDirectory() as tmp:
        cambiata = Path(tmp) / "informativa.md"
        cambiata.write_text(testo.replace(PRIMA, DOPO), "utf-8")
        informativa.TESTO = cambiata  # soltanto in questo script
        print("Rosa cambia la frase sui trasferimenti, e non la rimanda.")
        stampa(
            "Con l'informativa cambiata, la richiesta", settings, fascicolo_id
        )


if __name__ == "__main__":
    main(sys.argv[1])
