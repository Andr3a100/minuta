"""Lezione 33, errore deliberato: cancellare un fascicolo con le sole righe
del database.

    python percorso/cancella_le_righe.py 2026-074

Lavora su due copie temporanee del database e dei dati dello studio, che
poi cancella: lo studio non viene toccato. Nella prima il fascicolo si
cancella a mano, come si farebbe con sqlite3 (lezione B7): una DELETE per
ogni tabella, nell'ordine giusto. Nella seconda lo cancella Minuta, con una
regola di prova di zero anni al posto di quella dello studio. Poi, per
tutte e due, ciò che resta.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.conservazione import (  # noqa: E402
    cancella_fascicolo,
    carica_regola,
    data_in_lettere,
    residui,
)
from app.copie import percorso_database  # noqa: E402
from app.db import (  # noqa: E402
    Fascicolo,
    Utente,
    adesso,
    make_engine,
    make_session_factory,
)


# [libro:a-mano]
def cancella_a_mano(database: Path, codice: str) -> None:
    """Le righe del fascicolo, tabella per tabella: prima quelle che
    rimandano ad altre righe, per ultimo il fascicolo."""
    with sqlite3.connect(database) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        (f,) = conn.execute(
            "SELECT id FROM fascicoli WHERE codice = ?", (codice,)
        ).fetchone()
        for tabella in (
            "correzioni", "scadenze", "verifiche", "schede", "bozze",
            "risposte", "segnaposto", "persone", "documenti",
            "assegnazioni", "eventi",
        ):  # fmt: skip
            conn.execute(f"DELETE FROM {tabella} WHERE fascicolo_id = ?", (f,))
        conn.execute(
            "UPDATE uso_ai SET fascicolo_id = NULL WHERE fascicolo_id = ?",
            (f,),
        )
        conn.execute("DELETE FROM fascicoli WHERE id = ?", (f,))
    conn.close()


# [/libro:a-mano]


def cancella_con_minuta(settings, codice: str) -> None:
    prova = carica_regola()
    prova["fascicoli"] = {**prova["fascicoli"], "anni": 0}  # solo qui
    engine = make_engine(settings.database_url)
    with make_session_factory(engine)() as db:
        fascicolo = db.scalar(
            select(Fascicolo).where(Fascicolo.codice == codice)
        )
        avvocato = db.get(Utente, fascicolo.avvocato_id)
        cancella_fascicolo(
            db, settings, avvocato, fascicolo, prova, adesso().date()
        )
    engine.dispose()


def righe_rimaste(database: Path, codice: str) -> int:
    conn = sqlite3.connect(database)
    try:
        return conn.execute(
            "SELECT count(*) FROM fascicoli WHERE codice = ?", (codice,)
        ).fetchone()[0]
    finally:
        conn.close()  # su Windows un file aperto non si cancella


def resoconto(settings, codice: str) -> list[str]:
    engine = make_engine(settings.database_url)
    with make_session_factory(engine)() as db:
        trovati = residui(db, settings, carica_regola())
    engine.dispose()
    resta = righe_rimaste(percorso_database(settings), codice)
    nel_database = "c'è" if resta else "non c'è"
    orfani = len(trovati.file_senza_documento) or "nessuno"
    righe = [
        f"  il fascicolo nel database: {nel_database}",
        f"  originali senza documento: {orfani}",
    ]
    for c, quante, fino in trovati.nelle_copie:
        if c == codice:
            copie = "1 copia" if quante == 1 else f"{quante} copie"
            righe.append(
                f"  nelle copie di sicurezza: {copie}, fino al "
                f"{data_in_lettere(fino)}"
            )
    return righe


def main(codice: str) -> None:
    studio = load_settings()
    for titolo, cancella in (
        ("A mano, con le righe del database:", "a mano"),
        ("Con Minuta, con una regola di prova di zero anni:", "minuta"),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "studio.db"
            with sqlite3.connect(percorso_database(studio)) as origine:
                with sqlite3.connect(database) as copia:
                    origine.backup(copia)
                copia.close()
            origine.close()
            if Path(studio.data_dir).is_dir():
                shutil.copytree(studio.data_dir, Path(tmp) / "dati")
            prova = replace(
                studio,
                database_url=f"sqlite:///{database.as_posix()}",
                data_dir=str(Path(tmp) / "dati"),
            )
            if cancella == "a mano":
                cancella_a_mano(database, codice)
            else:
                cancella_con_minuta(prova, codice)
            print(titolo)
            print("\n".join(resoconto(prova, codice)))


if __name__ == "__main__":
    main(sys.argv[1])
