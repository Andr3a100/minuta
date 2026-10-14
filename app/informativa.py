"""L'informativa sull'intelligenza artificiale al cliente (lezione 34).

L'art. 13, comma 2, della legge 132/2025 vuole che il cliente riceva le
informazioni sui sistemi di intelligenza artificiale usati dal
professionista. Il testo dello studio sta in docs/informativa.md. Per ogni
fascicolo Minuta registra quando e come il cliente l'ha ricevuto, con
l'impronta del testo consegnato: la prova che la lezione 7 chiedeva di
conservare.

Senza la consegna, nessuna richiesta del fascicolo parte verso il modello.
E se il testo dello studio cambia dopo la consegna, non parte finché il
cliente non riceve quello nuovo: un'informativa vale per ciò che dice.

Il controllo sta davanti al modello, come il tetto della spesa (lezione
31): le funzioni che chiamano il modello non cambiano. Chi chiede per un
fascicolo lo dichiara con `per_il_fascicolo`, dal terminale e dal browser.
Le richieste senza fascicolo non portano i dati di un cliente, e non si
fermano.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from minuta.model import Modello, Risposta

from .conservazione import data_in_lettere
from .db import Fascicolo, Utente, adesso, make_engine, make_session_factory
from .registro import RichiestaNonAmmessa
from .web import registra_evento

TESTO = Path(__file__).resolve().parents[1] / "docs" / "informativa.md"
FASCICOLO: ContextVar[int | None] = ContextVar("fascicolo", default=None)


class InformativaMancante(RichiestaNonAmmessa):
    """Il cliente non ha ricevuto l'informativa di oggi: niente parte."""


def impronta_attuale(testo: Path | None = None) -> str:
    """L'impronta del testo di oggi, con gli a capo di ogni sistema resi
    uguali: su Windows Git può scrivere il file con «\\r\\n»."""
    dati = (testo or TESTO).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(dati).hexdigest()


def registra_consegna(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    giorno: date,
    modo: str,
) -> None:
    """La consegna dell'informativa di oggi al cliente del fascicolo."""
    if utente.ruolo not in ("avvocato", "segreteria"):
        raise InformativaMancante(
            "La consegna la registra un avvocato o la segreteria."
        )
    if giorno > adesso().date():
        raise InformativaMancante("La consegna non può essere futura.")
    modo = modo.strip()[:80]
    if not modo:
        raise InformativaMancante("Scrivi come è stata consegnata.")
    fascicolo.informativa_il = giorno
    fascicolo.informativa_impronta = impronta_attuale()
    fascicolo.informativa_modo = modo
    registra_evento(
        db,
        utente,
        fascicolo,
        "informativa",
        consegnata_il=giorno.isoformat(),
        modo=modo,
        impronta=fascicolo.informativa_impronta,
    )
    db.commit()


# [libro:informativa]
def controlla_informativa(fascicolo: Fascicolo) -> None:
    """La richiesta parte soltanto se il cliente ha ricevuto il testo di
    oggi: art. 13, comma 2, della legge 132/2025."""
    if fascicolo.informativa_il is None:
        raise InformativaMancante(
            f"{fascicolo.codice}: il cliente non ha ricevuto l'informativa "
            "sull'IA (art. 13, comma 2, legge 132/2025). La richiesta non "
            "parte."
        )
    if fascicolo.informativa_impronta != impronta_attuale():
        giorno = data_in_lettere(fascicolo.informativa_il)
        raise InformativaMancante(
            f"{fascicolo.codice}: l'informativa consegnata il {giorno} non "
            "è quella di oggi, che è cambiata dopo. La richiesta non parte "
            "finché il cliente non riceve la nuova."
        )


class ModelloConInformativa:
    """Il modello, con il controllo dell'informativa davanti."""

    def __init__(self, modello: Modello, database_url: str):
        self.modello = modello
        self.nome = modello.nome
        self.database_url = database_url

    def scrivi(self, sistema: str, richiesta: str) -> Risposta:
        fascicolo_id = FASCICOLO.get()
        if fascicolo_id is not None:
            engine = make_engine(self.database_url)
            try:
                with make_session_factory(engine)() as db:
                    controlla_informativa(db.get(Fascicolo, fascicolo_id))
            finally:
                engine.dispose()
        return self.modello.scrivi(sistema, richiesta)


# [/libro:informativa]


@contextmanager
def per_il_fascicolo(fascicolo_id: int | None) -> Iterator[None]:
    """Le richieste fatte qui dentro sono per questo fascicolo."""
    gettone = FASCICOLO.set(fascicolo_id)
    try:
        yield
    finally:
        FASCICOLO.reset(gettone)


class ModelloDelFascicolo:
    """Il modello, per le richieste di un fascicolo fatte dal terminale.
    Dal browser il fascicolo lo dichiara l'indirizzo della pagina."""

    def __init__(self, modello: Modello, fascicolo_id: int):
        self.modello = modello
        self.nome = modello.nome
        self.fascicolo_id = fascicolo_id

    def scrivi(self, sistema: str, richiesta: str) -> Risposta:
        with per_il_fascicolo(self.fascicolo_id):
            return self.modello.scrivi(sistema, richiesta)
