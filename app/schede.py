"""La scheda dell'atto in arrivo, nell'applicazione (lezione 18).

Come per le domande (app/invio.py), chi chiama ha già controllato chi
prepara la scheda e su quale documento. Le istruzioni della scheda e il
testo dell'atto, pagina per pagina, passano dalla preparazione del motore:
se resta qualcosa di riconoscibile, non parte niente. Le righe tornano con
i nomi veri, e Minuta le controlla sull'atto (minuta/scheda.py).

La scheda resta da verificare. Il praticante la prepara e ne toglie le
righe sbagliate; solo un avvocato la conferma, e solo quando nessuna riga
rimasta è segnalata. Ogni passaggio lascia la sua riga nel registro delle
attività, e la richiesta al modello la sua voce nel registro dell'uso
dell'AI, anche quando la risposta non è una scheda.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.invio import (
    SISTEMA,
    Preparato,
    prepara,
    ricomponi,
    segnaposto_sconosciuti,
)
from minuta.model import Modello
from minuta.scheda import (
    ISTRUZIONI,
    Riga,
    SchedaIlleggibile,
    a_pagine,
    controlla,
    leggi_risposta,
)

from .db import Documento, Fascicolo, Scheda, UsoAI, Utente, adesso
from .documenti import lettura_di
from .invio import (
    InvioBloccato,
    categorie,
    noti_del_fascicolo,
    salva_segnaposto,
    tabella_del_fascicolo,
    testo_nascosto,
)
from .registro import chiedi
from .web import registra_evento


class SchedaRifiutata(Exception):
    """L'operazione sulla scheda non è ammessa: il messaggio dice perché."""


@dataclass
class EsitoScheda:
    scheda: Scheda
    righe: list[Riga]
    preparato: Preparato  # il testo partito, con l'esito dei controlli
    arrivata: str  # la risposta com'è arrivata, con i segnaposto
    voce: UsoAI


def righe_di(scheda: Scheda) -> list[Riga]:
    return [Riga(**riga) for riga in json.loads(scheda.righe)]


def scrivi_righe(scheda: Scheda, righe: list[Riga]) -> None:
    scheda.righe = json.dumps([asdict(r) for r in righe], ensure_ascii=False)


def segnalate(righe: list[Riga]) -> list[int]:
    """I numeri delle righe con un problema, fra quelle rimaste."""
    return [
        n
        for n, r in enumerate(righe, start=1)
        if r.problemi and not r.tolta_da
    ]


def ultima_scheda(db: Session, documento: Documento) -> Scheda | None:
    return db.scalar(
        select(Scheda)
        .where(Scheda.documento_id == documento.id)
        .order_by(Scheda.id.desc())
    )


# [libro:prepara-scheda]
def prepara_scheda(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    documento: Documento,
    modello: Modello,
) -> EsitoScheda:
    pagine = [p["testo"] for p in lettura_di(documento)["pagine"]]
    noti = noti_del_fascicolo(db, fascicolo)
    testo = f"{ISTRUZIONI}\n\nDOCUMENTO: {documento.nome}\n{a_pagine(pagine)}"
    preparato = prepara(testo, noti, tabella_del_fascicolo(db, fascicolo))
    preparato.nascosto = testo_nascosto(documento)
    if preparato.bloccato:
        raise InvioBloccato(preparato)
    risposta, voce = chiedi(
        db,
        utente,
        fascicolo,
        modello,
        SISTEMA,
        preparato.testo,
        scopo="scheda dell'atto in arrivo",
        categorie=categorie(fascicolo, preparato),
        controllo=preparato.controllo(len(noti)),
    )
    salva_segnaposto(db, fascicolo, preparato.tabella)
    try:
        righe = leggi_risposta(risposta.testo)
    except SchedaIlleggibile:
        db.commit()  # la richiesta è partita: la sua voce resta
        raise
    for riga in righe:
        riga.testo = ricomponi(riga.testo, preparato.tabella)
        for segno in segnaposto_sconosciuti(riga.testo, preparato.tabella):
            riga.problemi.append(f"segnaposto che nessuno conosce: {segno}")
    controlla(righe, pagine)
    db.flush()  # il numero della voce del registro
    scheda = Scheda(
        fascicolo_id=fascicolo.id,
        documento_id=documento.id,
        uso_ai_id=voce.id,
        preparata_da_id=utente.id,
    )
    scrivi_righe(scheda, righe)
    db.add(scheda)
    registra_evento(
        db, utente, fascicolo, "scheda", nome=documento.nome, righe=len(righe)
    )
    db.commit()
    return EsitoScheda(scheda, righe, preparato, risposta.testo, voce)


# [/libro:prepara-scheda]


def togli_riga(
    db: Session, utente: Utente, fascicolo: Fascicolo, scheda: Scheda, n: int
) -> Riga:
    """Toglie una riga sbagliata dalla scheda: resta scritto chi l'ha tolta."""
    if utente.ruolo == "segreteria":
        raise SchedaRifiutata("La segreteria non modifica le schede.")
    if scheda.confermata_da_id is not None:
        raise SchedaRifiutata("La scheda è già confermata.")
    righe = righe_di(scheda)
    if not 1 <= n <= len(righe):
        raise SchedaRifiutata(f"La scheda non ha una riga {n}.")
    riga = righe[n - 1]
    if riga.tolta_da:
        raise SchedaRifiutata(f"La riga {n} è già stata tolta.")
    riga.tolta_da = utente.nome
    scrivi_righe(scheda, righe)
    registra_evento(
        db, utente, fascicolo, "riga tolta", riga=n, testo=riga.testo
    )
    db.commit()
    return riga


# [libro:conferma-scheda]
def conferma_scheda(
    db: Session, utente: Utente, fascicolo: Fascicolo, scheda: Scheda
) -> None:
    """La conferma è dell'avvocato, e solo di una scheda senza righe
    segnalate: chi conferma ha letto ogni riga con la sua pagina."""
    if utente.ruolo != "avvocato":
        raise SchedaRifiutata("Solo un avvocato conferma una scheda.")
    if scheda.confermata_da_id is not None:
        raise SchedaRifiutata("La scheda è già confermata.")
    restano = segnalate(righe_di(scheda))
    if restano:
        numeri = ", ".join(str(n) for n in restano)
        raise SchedaRifiutata(
            f"Restano righe segnalate: {numeri}. Toglile, o rifai la scheda."
        )
    scheda.confermata_da_id = utente.id
    scheda.confermata_il = adesso()
    registra_evento(db, utente, fascicolo, "scheda confermata", id=scheda.id)
    db.commit()


# [/libro:conferma-scheda]
