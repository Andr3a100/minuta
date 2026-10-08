"""Le domande sul fascicolo, nell'applicazione (lezione 21).

Chi chiama ha già controllato chi chiede e su quale fascicolo. Minuta
sceglie i passi dei documenti che contengono le parole della domanda; se
non ce n'è nessuno, salva la risposta «nel fascicolo non c'è» senza chiedere
niente a nessun modello. Altrimenti i passi, con chi chiede e la domanda,
passano dalla preparazione del motore (minuta/invio.py) e partono; le frasi
tornano con i nomi veri, e ogni citazione si controlla sul testo originale
della pagina (minuta/domande.py). Come per la scheda, la voce del registro
resta anche quando la risposta non è nella forma chiesta.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.domande import (
    ISTRUZIONI,
    Frase,
    Passo,
    RispostaIlleggibile,
    a_passi,
    controlla,
    leggi_risposta,
    scegli_passi,
)
from minuta.invio import (
    SISTEMA,
    Preparato,
    prepara,
    ricomponi,
    segnaposto_sconosciuti,
)
from minuta.model import Modello

from .db import Documento, Fascicolo, RispostaFascicolo, UsoAI, Utente
from .documenti import lettura_di
from .invio import (
    InvioBloccato,
    categorie,
    chi_chiede,
    noti_del_fascicolo,
    salva_segnaposto,
    tabella_del_fascicolo,
    testo_nascosto,
)
from .registro import RichiestaNonAmmessa, chiedi
from .web import registra_evento

NESSUN_PASSO = (
    "nessun passo dei documenti contiene le parole della domanda: nel "
    "fascicolo non c'è"
)


@dataclass
class EsitoDomanda:
    risposta: RispostaFascicolo
    passi: list[Passo]
    frasi: list[Frase]
    manca: str | None
    preparato: Preparato | None  # None: non è partito niente
    arrivata: str | None
    voce: UsoAI | None


def documenti_del_fascicolo(db: Session, fascicolo: Fascicolo):
    documenti = list(
        db.scalars(
            select(Documento)
            .where(Documento.fascicolo_id == fascicolo.id)
            .order_by(Documento.id)
        )
    )
    pagine = {
        d.nome: [p["testo"] for p in lettura_di(d)["pagine"]]
        for d in documenti
    }
    return documenti, pagine


def salva(db, utente, fascicolo, domanda, passi, frasi, manca, voce):
    risposta = RispostaFascicolo(
        fascicolo_id=fascicolo.id,
        domanda=domanda,
        passi=json.dumps(
            [(p.documento, p.pagina) for p in passi], ensure_ascii=False
        ),
        frasi=json.dumps([asdict(f) for f in frasi], ensure_ascii=False),
        manca=manca,
        uso_ai_id=voce.id if voce else None,
        chiesta_da_id=utente.id,
    )
    db.add(risposta)
    registra_evento(db, utente, fascicolo, "domanda", domanda=domanda)
    db.commit()
    return risposta


# [libro:domanda-fascicolo]
def domanda_sul_fascicolo(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    domanda: str,
    modello: Modello,
) -> EsitoDomanda:
    if utente.ruolo == "segreteria":
        raise RichiestaNonAmmessa("La segreteria non fa richieste al modello.")
    documenti, pagine = documenti_del_fascicolo(db, fascicolo)
    passi = scegli_passi(domanda, pagine)
    if not passi:  # non parte niente
        risposta = salva(
            db, utente, fascicolo, domanda, [], [], NESSUN_PASSO, None
        )
        return EsitoDomanda(risposta, [], [], NESSUN_PASSO, None, None, None)
    noti = noti_del_fascicolo(db, fascicolo)
    testo = (
        f"{ISTRUZIONI}\n\nCHI CHIEDE: {chi_chiede(utente, fascicolo)}\n"
        f"DOMANDA: {domanda}\n\n{a_passi(passi)}"
    )
    preparato = prepara(testo, noti, tabella_del_fascicolo(db, fascicolo))
    mandati = {p.documento for p in passi}
    preparato.nascosto = [
        f"{d.nome}, {n}"
        for d in documenti
        if d.nome in mandati
        for n in testo_nascosto(d)
    ]
    if preparato.bloccato:
        raise InvioBloccato(preparato)
    arrivata, voce = chiedi(
        db,
        utente,
        fascicolo,
        modello,
        SISTEMA,
        preparato.testo,
        scopo="domanda sul fascicolo",
        categorie=categorie(fascicolo, preparato),
        controllo=preparato.controllo(len(noti)),
    )
    salva_segnaposto(db, fascicolo, preparato.tabella)
    db.flush()  # il numero della voce del registro
    try:
        frasi, manca = leggi_risposta(arrivata.testo)
    except RispostaIlleggibile:
        db.commit()  # la richiesta è partita: la sua voce resta
        raise
    for frase in frasi:
        frase.testo = ricomponi(frase.testo, preparato.tabella)
        frase.citazione = ricomponi(frase.citazione, preparato.tabella)
        for segno in segnaposto_sconosciuti(
            frase.testo + frase.citazione, preparato.tabella
        ):
            frase.problemi.append(f"segnaposto che nessuno conosce: {segno}")
    controlla(frasi, passi)  # sul testo originale delle pagine
    manca = ricomponi(manca, preparato.tabella) if manca else None
    risposta = salva(db, utente, fascicolo, domanda, passi, frasi, manca, voce)
    return EsitoDomanda(
        risposta, passi, frasi, manca, preparato, arrivata.testo, voce
    )


# [/libro:domanda-fascicolo]
