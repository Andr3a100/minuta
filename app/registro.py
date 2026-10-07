"""Il registro dell'uso dell'AI: una voce per ogni richiesta al modello.

Le regole sono quelle della lezione 8: la voce si scrive quando la
richiesta parte, si aggiunge e non si corregge, e non contiene mai il testo
inviato, solo la sua impronta. In più c'è ciò che il pilota non sapeva: chi
ha fatto la richiesta. Dalla lezione 17 il testo, prima di partire, passerà
dalla pseudonimizzazione; finché non c'è, nessuna pagina chiama il modello.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy.orm import Session

from minuta.model import Modello, Risposta

from .db import UsoAI

PREZZI = Path(__file__).resolve().parent.parent / "config" / "prezzi.json"


class RichiestaNonAmmessa(Exception):
    """Chi chiede non può fare richieste al modello."""


def costo_stimato(modello: str, token_in, token_out) -> float | None:
    """Il costo a prezzi standard, dalla scheda del fornitore in config/.

    Non comprende le maggiorazioni del contratto, per esempio quella per la
    residenza dei dati in Europa: i conti veri sono nella lezione 31.
    """
    prezzi = json.loads(PREZZI.read_text("utf-8")).get(modello)
    if prezzi is None or token_in is None or token_out is None:
        return None
    # I prezzi della scheda sono in dollari per milione di token.
    dollari = token_in * prezzi["ingresso"] + token_out * prezzi["uscita"]
    return round(dollari / 1_000_000, 6)


# [libro:chiedi]
def chiedi(
    db: Session,
    utente,
    fascicolo,
    modello: Modello,
    sistema: str,
    richiesta: str,
    *,
    scopo: str,
    categorie: str,
    controllo: str,
) -> tuple[Risposta, UsoAI]:
    """Fa la richiesta al modello e ne scrive la voce nel registro.

    La voce entra nella transazione di chi chiama: se l'azione che ha
    chiesto la risposta non viene salvata, la voce non resta.
    """
    if utente.ruolo == "segreteria":
        raise RichiestaNonAmmessa("La segreteria non fa richieste al modello.")
    inviato = sistema + "\n\n" + richiesta
    risposta = modello.scrivi(sistema, richiesta)
    voce = UsoAI(
        utente_id=utente.id,
        fascicolo_id=fascicolo.id if fascicolo else None,
        modello=risposta.modello,
        categorie=categorie,
        scopo=scopo,
        impronta=hashlib.sha256(inviato.encode("utf-8")).hexdigest(),
        caratteri=len(inviato),
        controllo=controllo,
        token_in=risposta.token_in,
        token_out=risposta.token_out,
        costo_usd=costo_stimato(
            risposta.modello, risposta.token_in, risposta.token_out
        ),
    )
    db.add(voce)
    return risposta, voce


# [/libro:chiedi]
