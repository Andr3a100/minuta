"""I muri dello studio (lezione 32): fra le materie e fra i clienti.

Ogni persona dello studio lavora nelle sue materie: un avvocato civilista
non è assegnato a un fascicolo penale, e il penale lo vede soltanto chi ci
lavora. Le materie di una persona le decide un avvocato; senza materie,
una persona lavora in tutte, come nelle versioni di prima.

Fra i clienti, il muro è il conflitto d'interessi (art. 24 del codice
deontologico forense): un nome che in un fascicolo è cliente e in un altro
sta dall'altra parte, o in qualunque altro ruolo, si segnala prima che il
fascicolo si apra o la persona entri nell'elenco. Minuta non decide se il
conflitto c'è: lo valuta un avvocato, e la sua valutazione resta nel
registro. In una società tra avvocati il dovere di astensione vale per
tutti i suoi avvocati (art. 24, comma 5): il controllo guarda tutto lo
studio.
"""

from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import Assegnazione, Fascicolo, PersonaFascicolo, Utente
from .rules import ETICHETTE_MATERIE
from .web import registra_evento


class MuroRifiutato(Exception):
    """L'operazione attraversa un muro: il messaggio dice quale."""


def materie_di(utente: Utente) -> set[str] | None:
    """Le materie di una persona; None, se lavora in tutte."""
    return set(utente.materie.split()) if utente.materie else None


def imposta_materie(
    db: Session, chi: Utente, utente: Utente, materie: list[str]
) -> list[str]:
    """Le materie di una persona. Le assegnazioni ai fascicoli di altre
    materie si tolgono: il muro vale anche per chi c'era già."""
    if chi.ruolo != "avvocato":
        raise MuroRifiutato("Le materie di una persona le decide un avvocato.")
    sconosciute = [m for m in materie if m not in ETICHETTE_MATERIE]
    if sconosciute:
        raise MuroRifiutato(f"Materia sconosciuta: {', '.join(sconosciute)}.")
    utente.materie = " ".join(sorted(set(materie)))
    tolti = []
    if materie:
        fuori = db.scalars(
            select(Fascicolo)
            .join(Assegnazione, Assegnazione.fascicolo_id == Fascicolo.id)
            .where(
                Assegnazione.utente_id == utente.id,
                Fascicolo.materia.not_in(materie),
            )
        ).all()
        for fascicolo in fuori:
            db.execute(
                delete(Assegnazione).where(
                    Assegnazione.fascicolo_id == fascicolo.id,
                    Assegnazione.utente_id == utente.id,
                )
            )
            tolti.append(fascicolo.codice)
    registra_evento(
        db,
        chi,
        None,
        "materie",
        persona=utente.nome_utente,
        materie=utente.materie,
        tolti=tolti,
    )
    db.commit()
    return tolti


def controlla_materia(utente: Utente, materia: str) -> None:
    materie = materie_di(utente)
    if materie is not None and materia not in materie:
        raise MuroRifiutato(
            f"{utente.nome} non lavora nella materia {materia}: il fascicolo "
            "resta fuori dal suo muro."
        )


def normale(nome: str) -> str:
    """«Termocucine Secchia S.r.l.» e «termocucine secchia srl» sono lo
    stesso nome."""
    return re.sub(r"[\W_]+", "", nome.casefold())


# [libro:conflitti]
def conflitti(
    db: Session, nome: str, ruolo: str, fascicolo_id: int | None = None
) -> list[str]:
    """Dove il nome sta dall'altra parte: se è cliente, i fascicoli in cui
    ha un altro ruolo; se ha un altro ruolo, quelli in cui è cliente."""
    cliente = ruolo == "cliente"
    trovati = []
    righe = db.execute(
        select(PersonaFascicolo, Fascicolo)
        .join(Fascicolo, Fascicolo.id == PersonaFascicolo.fascicolo_id)
        .order_by(Fascicolo.codice)
    )
    for persona, fascicolo in righe:
        if fascicolo.id == fascicolo_id or normale(persona.nome) != normale(
            nome
        ):
            continue
        if (persona.ruolo == "cliente") != cliente:
            dove = f"{fascicolo.codice} ({fascicolo.cliente})"
            trovati.append(f"{dove}, come {persona.ruolo}")
    return trovati


# [/libro:conflitti]


def ferma_se_conflitto(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo | None,
    nome: str,
    ruolo: str,
    valutazione: str | None,
) -> None:
    """Un possibile conflitto ferma l'operazione, salvo la valutazione
    scritta di un avvocato, che resta nel registro."""
    trovati = conflitti(db, nome, ruolo, fascicolo.id if fascicolo else None)
    if not trovati:
        return
    if not valutazione:
        raise MuroRifiutato(
            f"Possibile conflitto d'interessi: {nome} è già in "
            f"{'; '.join(trovati)}. Lo valuta un avvocato (art. 24 del "
            "codice deontologico forense)."
        )
    if utente.ruolo != "avvocato":
        raise MuroRifiutato("Un conflitto d'interessi lo valuta un avvocato.")
    registra_evento(
        db,
        utente,
        fascicolo,
        "conflitto_valutato",
        nome=nome,
        dove=trovati,
        valutazione=valutazione,
    )
