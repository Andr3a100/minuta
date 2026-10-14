"""Le misure della valutazione d'impatto, controllate (lezione 35).

La valutazione d'impatto di Studio Meridiana, in docs/valutazione-impatto.md,
dichiara le misure che rendono accettabile il rischio. Una misura scritta
non è una misura vera: dove si può, Minuta la controlla sui propri dati,
e dice se è verificata o smentita. Le altre si controllano a mano, e
Minuta lo dice. Se un controllo smentisce una misura, la valutazione non
vale finché la misura non torna vera.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .conservazione import carica_regola, residui
from .copie import (
    CopiaRifiutata,
    copie_della_cartella,
    fatta_il,
    verifica_copia,
)
from .db import Assegnazione, Fascicolo, UsoAI, Utente
from .informativa import impronta_attuale
from .muri import materie_di

VERIFICATA, SMENTITA, A_MANO = "verificata", "smentita", "a mano"
FUGHE = re.compile(r"fughe: (\d+); nomi fuori elenco: (\d+)")


@dataclass
class Esito:
    misura: str
    titolo: str
    stato: str
    dettaglio: str


def informativa(db: Session) -> Esito:
    aperti = list(
        db.scalars(select(Fascicolo).where(Fascicolo.stato != "chiuso"))
    )
    oggi = impronta_attuale()
    informati = sum(f.informativa_impronta == oggi for f in aperti)
    return Esito(
        "M1",
        "informativa al cliente",
        VERIFICATA,
        f"fascicoli aperti con l'informativa di oggi: {informati} su "
        f"{len(aperti)}; negli altri nessuna richiesta parte",
    )


def segnaposto(db: Session) -> Esito:
    """Nel registro, ogni richiesta partita senza fughe e senza nomi
    fuori elenco."""
    sospette = []
    for voce in db.scalars(
        select(UsoAI).where(UsoAI.fascicolo_id.isnot(None))
    ):
        trovato = FUGHE.search(voce.controllo)
        if trovato and (int(trovato.group(1)) or int(trovato.group(2))):
            sospette.append(f"n. {voce.id}")
    if sospette:
        return Esito(
            "M2",
            "segnaposto e blocco dell'invio",
            SMENTITA,
            f"voci del registro con fughe: {', '.join(sospette)}",
        )
    return Esito(
        "M2",
        "segnaposto e blocco dell'invio",
        VERIFICATA,
        "nessuna voce del registro con fughe o nomi fuori elenco",
    )


# [libro:penale]
def muro_del_penale(db: Session) -> Esito:
    """Nei fascicoli penali lavora soltanto chi ha la materia penale. Chi
    non ha materie lavora in tutte: per il penale non basta."""
    fuori = []
    for fascicolo, persona in db.execute(
        select(Fascicolo, Utente)
        .join(Assegnazione, Assegnazione.fascicolo_id == Fascicolo.id)
        .join(Utente, Utente.id == Assegnazione.utente_id)
        .where(Fascicolo.materia == "penale")
        .order_by(Fascicolo.codice, Utente.nome)
    ):
        if "penale" not in (materie_di(persona) or set()):
            fuori.append(f"{persona.nome} in {fascicolo.codice}")
    if fuori:
        return Esito(
            "M3",
            "il muro del penale",
            SMENTITA,
            "assegnati senza la materia penale: " + ", ".join(fuori),
        )
    return Esito(
        "M3",
        "il muro del penale",
        VERIFICATA,
        "nei fascicoli penali soltanto persone con la materia penale",
    )


# [/libro:penale]


def copie(settings: Settings) -> Esito:
    elenco = copie_della_cartella(Path(settings.copie_dir))
    if not elenco:
        return Esito("M4", "copie di sicurezza", SMENTITA, "nessuna copia")
    ultima = max(elenco, key=fatta_il)
    try:
        problemi = verifica_copia(ultima).problemi
    except CopiaRifiutata as exc:
        problemi = [str(exc)]
    if problemi:
        return Esito(
            "M4",
            "copie di sicurezza",
            SMENTITA,
            f"{ultima.name} non si ripristina: {'; '.join(problemi)}",
        )
    return Esito(
        "M4",
        "copie di sicurezza",
        VERIFICATA,
        f"l'ultima, {ultima.name}, si ripristina",
    )


def conservazione(db: Session, settings: Settings) -> Esito:
    regola = carica_regola()
    if not isinstance(regola["fascicoli"]["anni"], int):
        return Esito(
            "M5",
            "conservazione e cancellazione",
            SMENTITA,
            "la regola dei fascicoli è ancora da decidere",
        )
    trovati = residui(db, settings, regola)
    orfani = trovati.file_senza_documento
    if orfani:
        return Esito(
            "M5",
            "conservazione e cancellazione",
            SMENTITA,
            f"originali senza documento: {len(orfani)}",
        )
    return Esito(
        "M5",
        "conservazione e cancellazione",
        VERIFICATA,
        f"{regola['fascicoli']['anni']} anni dalla chiusura; nessun residuo",
    )


A_MANO_ELENCO = (
    ("M6", "fonte di ogni dato, approvazione", "lezioni 24 e 26"),
    ("M7", "trasferimenti fuori dallo SEE", "il contratto, lezione 6"),
    ("M8", "copie cifrate fuori dal server", "chi amministra il server"),
    ("M9", "alfabetizzazione", "la scheda degli strumenti, lezione 9"),
)


def esamina(db: Session, settings: Settings) -> list[Esito]:
    esiti = [
        informativa(db),
        segnaposto(db),
        muro_del_penale(db),
        copie(settings),
        conservazione(db, settings),
    ]
    esiti += [Esito(m, t, A_MANO, d) for m, t, d in A_MANO_ELENCO]
    return esiti
