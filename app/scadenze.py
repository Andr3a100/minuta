"""Le scadenze del fascicolo, nell'applicazione (lezione 19).

La data di partenza viene da una sola fonte: la riga della data della
notificazione nella scheda confermata del documento. Se la scheda non è
confermata, o la data non risulta, Minuta non calcola: chi ha bisogno della
scadenza cerca il documento della notificazione e ne fa la scheda. Il
calcolo non chiede niente a nessun modello: lo fanno le regole del file
config/termini.json (minuta/scadenze.py). Per questo lo può fare anche la
segreteria, che tiene lo scadenziario; la conferma resta dell'avvocato.
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.scadenze import Calcolo, calcola, carica_regole
from minuta.scheda import date_in

from .db import Documento, Fascicolo, Scadenza, Utente, adesso
from .schede import righe_di, ultima_scheda
from .web import registra_evento


class ScadenzaRifiutata(Exception):
    """La scadenza non si calcola o non si conferma: il messaggio dice
    perché."""


# [libro:partenza]
def data_di_partenza(righe) -> tuple[date, int]:
    """La data della notificazione, dalla scheda: una riga rimasta, con una
    data sola. Il numero della riga serve a citarla."""
    trovate = [
        (n, riga)
        for n, riga in enumerate(righe, start=1)
        if not riga.tolta_da
        and riga.voce == "date"
        and "notific" in riga.testo.casefold()
        and not riga.manca
    ]
    date_trovate = {d for _n, riga in trovate for d in date_in(riga.testo)}
    if not date_trovate:
        raise ScadenzaRifiutata(
            "La data della notificazione non risulta dalla scheda: cercala "
            "nel documento della notificazione, e fanne la scheda."
        )
    if len(date_trovate) > 1:
        raise ScadenzaRifiutata(
            "La scheda dà più date di notificazione: ne resta una sola, "
            "quella che l'avvocato ha letto."
        )
    return date_trovate.pop(), trovate[0][0]


# [/libro:partenza]


def calcola_scadenza(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    documento: Documento,
    termine: str,
) -> tuple[Scadenza, Calcolo, int]:
    """Calcola e salva la scadenza, da verificare. Restituisce anche il
    calcolo e la riga della scheda da cui viene la partenza."""
    scheda = ultima_scheda(db, documento)
    if scheda is None or scheda.confermata_da_id is None:
        raise ScadenzaRifiutata(
            f"La scheda di {documento.nome} non è confermata: la data di "
            "partenza la conferma un avvocato."
        )
    partenza, riga = data_di_partenza(righe_di(scheda))
    calcolo = calcola(termine, partenza, carica_regole())
    scadenza = Scadenza(
        fascicolo_id=fascicolo.id,
        documento_id=documento.id,
        scheda_id=scheda.id,
        termine=calcolo.termine,
        norma=calcolo.norma,
        partenza=partenza,
        scadenza=calcolo.scadenza,
        passaggi=json.dumps(calcolo.passaggi, ensure_ascii=False),
        da_decidere=calcolo.da_decidere,
        calcolata_da_id=utente.id,
    )
    db.add(scadenza)
    db.flush()
    registra_evento(
        db,
        utente,
        fascicolo,
        "scadenza",
        termine=calcolo.termine,
        scadenza=calcolo.scadenza.isoformat() if calcolo.scadenza else None,
    )
    db.commit()
    return scadenza, calcolo, riga


def ultima_scadenza(db: Session, documento: Documento) -> Scadenza | None:
    return db.scalar(
        select(Scadenza)
        .where(Scadenza.documento_id == documento.id)
        .order_by(Scadenza.id.desc())
    )


def conferma_scadenza(
    db: Session, utente: Utente, fascicolo: Fascicolo, scadenza: Scadenza
) -> None:
    """La conferma è dell'avvocato, e solo di una data calcolata."""
    if utente.ruolo != "avvocato":
        raise ScadenzaRifiutata("Solo un avvocato conferma una scadenza.")
    if scadenza.confermata_da_id is not None:
        raise ScadenzaRifiutata("La scadenza è già confermata.")
    if scadenza.scadenza is None:
        raise ScadenzaRifiutata(
            f"Minuta non ha calcolato una data: {scadenza.da_decidere}. "
            "La decisione è dell'avvocato, fuori da Minuta."
        )
    scadenza.confermata_da_id = utente.id
    scadenza.confermata_il = adesso()
    registra_evento(
        db, utente, fascicolo, "scadenza confermata", termine=scadenza.termine
    )
    db.commit()
