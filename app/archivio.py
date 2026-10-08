"""L'archivio dello studio, nell'applicazione (lezione 22).

Un avvocato carica gli atti firmati di ieri, con l'indice dello studio che
dice, per ciascuno, le persone da nascondere. Minuta legge le pagine e i
dati dell'atto, conserva l'originale con la sua impronta come nome e lascia
la riga nel registro delle attività. Avvocati e praticanti cercano per
parole, tipo, autore e periodo; la segreteria no, perché l'archivio porta i
fatti di tutti i clienti dello studio. Cercare non manda niente a nessuno.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta import documenti as motore
from minuta.archivio import (
    AttoLetto,
    Trovato,
    cerca,
    dati_dell_atto,
    filtra,
    tipo_del_nome,
)

from .config import Settings
from .db import AttoArchivio, Utente
from .documenti import cartella_dati
from .web import registra_evento


class ArchivioRifiutato(Exception):
    """L'operazione sull'archivio non è ammessa: il messaggio dice perché."""


def puo_leggere(utente: Utente) -> bool:
    return utente.ruolo in ("avvocato", "praticante")


def avvocati_dello_studio(db: Session) -> list[dict]:
    """Gli avvocati, come li chiede la lettura degli atti: chi firma è
    l'autore."""
    return [
        {"id": u.nome_utente, "nome": u.nome}
        for u in db.scalars(select(Utente).where(Utente.ruolo == "avvocato"))
    ]


# [libro:carica-atto]
def carica_atto(
    db: Session,
    settings: Settings,
    utente: Utente,
    percorso: Path,
    persone: list[str] | None,
) -> AttoArchivio:
    """Un atto entra nell'archivio solo con le sue persone da nascondere:
    senza, le sue pagine non potrebbero mai partire pseudonimizzate."""
    if utente.ruolo != "avvocato":
        raise ArchivioRifiutato("L'archivio lo carica un avvocato.")
    if not persone:
        raise ArchivioRifiutato(
            "manca nell'indice: senza le persone da nascondere non entra."
        )
    dati = percorso.read_bytes()
    impronta = hashlib.sha256(dati).hexdigest()
    gia = db.scalar(
        select(AttoArchivio).where(AttoArchivio.impronta == impronta)
    )
    if gia is not None:
        raise ArchivioRifiutato(f"è già nell'archivio, come {gia.nome}.")
    lettura = motore.leggi(percorso.name, dati, cartella_dati(settings))
    letti = dati_dell_atto(percorso, avvocati_dello_studio(db))
    autore = db.scalar(
        select(Utente).where(Utente.nome_utente == letti["autore"])
    )
    cartella = cartella_dati(settings) / "archivio"
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / impronta).write_bytes(dati)  # l'originale, com'era
    atto = AttoArchivio(
        nome=percorso.name,
        impronta=impronta,
        tipo=letti["tipo"],
        autore_id=autore.id if autore else None,
        data=letti["data"],
        giudice=letti["giudice"],
        valore=letti["valore"],
        pagine=json.dumps(
            [p.testo for p in lettura.pagine], ensure_ascii=False
        ),
        persone=json.dumps(persone, ensure_ascii=False),
        nascosti=len(lettura.nascosti),
        caricato_da_id=utente.id,
    )
    db.add(atto)
    db.flush()
    registra_evento(
        db, utente, None, "archivio", nome=percorso.name, impronta=impronta
    )
    db.commit()  # l'atto e la sua riga, insieme o per niente
    return atto


# [/libro:carica-atto]


def atti_dell_archivio(db: Session) -> list[AttoArchivio]:
    return list(db.scalars(select(AttoArchivio).order_by(AttoArchivio.id)))


def letti(db: Session, atti: list[AttoArchivio]) -> list[AttoLetto]:
    """Gli atti come li chiede la ricerca del motore."""
    utenti = {u.id: u.nome_utente for u in db.scalars(select(Utente))}
    return [
        AttoLetto(
            numero=a.id,
            tipo=a.tipo,
            autore=utenti.get(a.autore_id),
            data=a.data,
            pagine=json.loads(a.pagine),
        )
        for a in atti
    ]


def persone_di(atto: AttoArchivio) -> dict[str, str]:
    """I nomi da nascondere di un atto, con il loro tipo di segnaposto."""
    return {n: tipo_del_nome(n) for n in json.loads(atto.persone)}


def scelti(
    db: Session,
    tipo: str | None = None,
    autore: str | None = None,
    dal: date | None = None,
    al: date | None = None,
) -> list[AttoLetto]:
    return filtra(letti(db, atti_dell_archivio(db)), tipo, autore, dal, al)


def cerca_nell_archivio(
    db: Session,
    utente: Utente,
    testo: str,
    tipo: str | None = None,
    autore: str | None = None,
    dal: date | None = None,
    al: date | None = None,
) -> list[Trovato]:
    if not puo_leggere(utente):
        raise ArchivioRifiutato("La segreteria non consulta l'archivio.")
    return cerca(testo, scelti(db, tipo, autore, dal, al))
