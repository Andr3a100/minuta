"""Lezione 15, errore deliberato: salvare la modifica prima della sua riga.

    python percorso/rompi_registro.py

Lavora su un database temporaneo, che poi cancella: il database dello
studio non viene toccato. Fa due volte lo stesso cambio di stato di un
fascicolo mentre la scrittura della riga nel registro delle attività si
guasta, per finta: una volta con la modifica e la riga nella stessa
transazione, come fa Minuta, e una volta salvando la modifica prima di
scrivere la riga.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, update  # noqa: E402

from app.db import (  # noqa: E402
    Evento,
    Fascicolo,
    adesso,
    make_engine,
    make_session_factory,
)
from app.manage import crea_prova, crea_utente  # noqa: E402
from app.migrations import migra  # noqa: E402


def guasto():
    raise RuntimeError("guasto simulato mentre si scrive la riga")


# [libro:rompi]
def cambia_stato(sessioni, codice: str, salva_prima: bool) -> None:
    with sessioni() as db:
        fascicolo = db.scalar(
            select(Fascicolo).where(Fascicolo.codice == codice)
        )
        try:
            db.execute(
                update(Fascicolo)
                .where(Fascicolo.id == fascicolo.id)
                .values(
                    stato="in_studio",
                    versione=Fascicolo.versione + 1,
                    aggiornato_il=adesso(),
                )
            )
            if salva_prima:
                db.commit()  # l'errore: la modifica è salvata da sola
            guasto()  # qui Minuta scrive la riga del registro
            db.commit()  # la modifica e la riga, insieme
        except RuntimeError as errore:
            print(f"  errore: {errore}")
    with sessioni() as db:
        fascicolo = db.scalar(
            select(Fascicolo).where(Fascicolo.codice == codice)
        )
        righe = db.scalar(
            select(func.count())
            .select_from(Evento)
            .where(
                Evento.fascicolo_id == fascicolo.id, Evento.azione == "stato"
            )
        )
    print(
        f"  {codice}: stato {fascicolo.stato}, versione {fascicolo.versione}, "
        f"righe del cambio nel registro {righe}"
    )


# [/libro:rompi]


def main() -> int:
    with tempfile.TemporaryDirectory() as cartella:
        file = (Path(cartella) / "prova.db").as_posix()
        engine = make_engine(f"sqlite:///{file}")
        migra(engine)
        sessioni = make_session_factory(engine)
        with sessioni() as db:
            crea_utente(db, "sarti", "avvocato", "Elena Sarti", "x" * 20)
            crea_prova(db, production=False)
        print("La modifica e la sua riga nella stessa transazione:")
        cambia_stato(sessioni, "2026-071", salva_prima=False)
        print("La modifica salvata prima di scrivere la sua riga:")
        cambia_stato(sessioni, "2026-072", salva_prima=True)
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
