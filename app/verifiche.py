"""Le verifiche dei documenti, nell'applicazione (lezione 20).

Avvocati e praticanti preparano le verifiche di un documento scegliendo il
tipo di atto: Minuta copia le domande di config/verifiche.json e le riempie
con i fatti della scheda confermata, le somme rifatte e le scadenze del
documento. Niente parte verso un modello. Lo stato di ogni domanda lo
decide l'avvocato, e ogni decisione lascia la sua riga nel registro delle
attività.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.scadenze import in_lettere
from minuta.verifiche import STATI, carica_domande, prepara, tipo_di

from .db import Documento, Fascicolo, Scadenza, Utente, Verifica
from .documenti import lettura_di
from .schede import righe_di, ultima_scheda
from .web import registra_evento


class VerificaRifiutata(Exception):
    """L'operazione sulle verifiche non è ammessa: il messaggio dice
    perché."""


def scadenze_del_documento(
    db: Session, documento: Documento, nomi: dict
) -> list[str]:
    righe = []
    for s in db.scalars(
        select(Scadenza)
        .where(Scadenza.documento_id == documento.id)
        .order_by(Scadenza.id)
    ):
        if s.scadenza is None:
            righe.append(f"{s.termine}: decide l'avvocato, {s.da_decidere}")
            continue
        stato = (
            f"confermata da {nomi.get(s.confermata_da_id, '')}"
            if s.confermata_da_id
            else "da verificare"
        )
        righe.append(f"{s.termine}: {in_lettere(s.scadenza)}, {stato}")
    return righe


def prepara_verifiche(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    documento: Documento,
    tipo: str,
) -> Verifica:
    if utente.ruolo == "segreteria":
        raise VerificaRifiutata("La segreteria non prepara le verifiche.")
    domande = carica_domande()
    tipo = tipo_di(domande, tipo)
    pagine = [p["testo"] for p in lettura_di(documento)["pagine"]]
    scheda = ultima_scheda(db, documento)
    confermata = scheda is not None and scheda.confermata_da_id is not None
    nomi = {u.id: u.nome for u in db.scalars(select(Utente))}
    riempite = prepara(
        tipo,
        domande,
        pagine,
        righe_di(scheda) if confermata else None,
        scadenze_del_documento(db, documento, nomi),
    )
    verifica = Verifica(
        fascicolo_id=fascicolo.id,
        documento_id=documento.id,
        tipo=tipo,
        domande=json.dumps(riempite, ensure_ascii=False),
        preparata_da_id=utente.id,
    )
    db.add(verifica)
    db.flush()
    registra_evento(
        db, utente, fascicolo, "verifiche", nome=documento.nome, tipo=tipo
    )
    db.commit()
    return verifica


def ultima_verifica(db: Session, documento: Documento) -> Verifica | None:
    return db.scalar(
        select(Verifica)
        .where(Verifica.documento_id == documento.id)
        .order_by(Verifica.id.desc())
    )


def decidi_domanda(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    verifica: Verifica,
    numero: int,
    stato: str,
) -> dict:
    """Lo stato di una domanda: lo decide l'avvocato."""
    if utente.ruolo != "avvocato":
        raise VerificaRifiutata(
            "Lo stato di una verifica lo decide l'avvocato."
        )
    if stato not in STATI:
        raise VerificaRifiutata(f"Gli stati sono: {', '.join(STATI)}.")
    domande = json.loads(verifica.domande)
    if not 1 <= numero <= len(domande):
        raise VerificaRifiutata(
            f"Le verifiche non hanno una domanda {numero}."
        )
    domanda = domande[numero - 1]
    domanda["stato"], domanda["deciso_da"] = stato, utente.nome
    verifica.domande = json.dumps(domande, ensure_ascii=False)
    registra_evento(
        db, utente, fascicolo, "verifica", domanda=numero, stato=stato
    )
    db.commit()
    return domanda
