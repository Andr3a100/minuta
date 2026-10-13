"""Il glossario del fascicolo, nell'applicazione (lezione 29)."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from minuta.domande import parole

from .db import Fascicolo, Utente
from .web import registra_evento


class GlossarioRifiutato(Exception):
    """La voce non entra nel glossario: il messaggio dice perché."""


def glossario_di(fascicolo: Fascicolo) -> dict[str, list[str]]:
    return json.loads(fascicolo.glossario or "{}")


def decidi_voce(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    parola: str,
    equivalenti: list[str],
) -> dict[str, list[str]]:
    """Una voce del glossario: la decide l'avvocato del fascicolo, che
    conosce il caso. Senza equivalenti, la voce si toglie."""
    if utente.id != fascicolo.avvocato_id:
        raise GlossarioRifiutato(
            "Il glossario lo decide l'avvocato del fascicolo."
        )
    if not parole(parola) or (
        equivalenti and not parole(" ".join(equivalenti))
    ):
        raise GlossarioRifiutato(
            "Servono parole di almeno quattro lettere: le altre Minuta non "
            "le confronta."
        )
    glossario = glossario_di(fascicolo)
    if equivalenti:
        glossario[parola] = equivalenti
    else:
        glossario.pop(parola, None)
    fascicolo.glossario = json.dumps(glossario, ensure_ascii=False)
    registra_evento(
        db,
        utente,
        fascicolo,
        "glossario",
        parola=parola,
        equivalenti=equivalenti,
    )
    db.commit()
    return glossario
