"""Lo stile degli avvocati, nell'applicazione (lezione 23).

Ogni avvocato calcola il proprio profilo dagli atti dell'archivio che ha
firmato: Minuta conta, senza chiedere niente a nessun modello. Le formule
con una norma restano da decidere finché l'avvocato non dice se sono stile,
da tenere, o diritto, che dipende dal caso, da togliere; finché ne resta
una, il profilo non si conferma. Avvocati e praticanti lo leggono; la
segreteria no. Ogni passaggio lascia la sua riga nel registro delle
attività.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.stile import calcola, generico

from .archivio import persone_di, puo_leggere
from .db import AttoArchivio, ProfiloStile, Utente, adesso
from .web import registra_evento

STATI = ("stile", "tolta")


class StileRifiutato(Exception):
    """L'operazione sul profilo non è ammessa: il messaggio dice perché."""


def ultimo_profilo(db: Session, autore: Utente) -> ProfiloStile | None:
    return db.scalar(
        select(ProfiloStile)
        .where(ProfiloStile.autore_id == autore.id)
        .order_by(ProfiloStile.id.desc())
    )


def letto(profilo: ProfiloStile) -> dict:
    return json.loads(profilo.contenuto)


# [libro:calcola-profilo]
def calcola_profilo(db: Session, utente: Utente) -> ProfiloStile:
    """Il profilo di chi lo chiede, dai suoi atti dell'archivio, con i nomi
    nascosti da segnaposto senza numero."""
    if utente.ruolo != "avvocato":
        raise StileRifiutato("Il profilo dello stile è di un avvocato.")
    atti = list(
        db.scalars(
            select(AttoArchivio)
            .where(AttoArchivio.autore_id == utente.id)
            .order_by(AttoArchivio.id)
        )
    )
    if len(atti) < 2:
        raise StileRifiutato(
            "Servono almeno due atti firmati nell'archivio: una formula "
            "è tale se torna."
        )
    studio = {
        u.nome: "PERSONA"
        for u in db.scalars(select(Utente))
        if len(u.nome.split()) >= 2
    }
    testi = {
        a.id: (
            a.tipo,
            generico("\n".join(json.loads(a.pagine)), studio | persone_di(a)),
        )
        for a in atti
    }
    profilo = ProfiloStile(
        autore_id=utente.id,
        contenuto=json.dumps(asdict(calcola(testi)), ensure_ascii=False),
    )
    db.add(profilo)
    registra_evento(db, utente, None, "stile", atti=len(atti))
    db.commit()
    return profilo


# [/libro:calcola-profilo]


def proprio(db: Session, utente: Utente) -> ProfiloStile:
    profilo = ultimo_profilo(db, utente)
    if profilo is None:
        raise StileRifiutato(
            "Non c'è ancora un profilo: calcolalo con il comando stile."
        )
    return profilo


def decidi_formule(
    db: Session, utente: Utente, numeri: list[int], stato: str
) -> list[dict]:
    """Tenere una formula nello stile o toglierla: lo decide il suo
    avvocato, sul proprio profilo."""
    if stato not in STATI:
        raise StileRifiutato(f"Gli stati sono: {', '.join(STATI)}.")
    profilo = proprio(db, utente)
    dati = letto(profilo)
    formule = dati["formule"]
    fuori = [n for n in numeri if not 1 <= n <= len(formule)]
    if fuori:
        raise StileRifiutato(
            f"Il profilo non ha la formula {fuori[0]}: sono {len(formule)}."
        )
    for n in numeri:
        formule[n - 1]["stato"] = stato
    profilo.contenuto = json.dumps(dati, ensure_ascii=False)
    profilo.confermato_il = None  # cambiato: va riletto e confermato
    registra_evento(db, utente, None, "formule", numeri=numeri, stato=stato)
    db.commit()
    return [formule[n - 1] for n in numeri]


# [libro:conferma-profilo]
def conferma_profilo(db: Session, utente: Utente) -> ProfiloStile:
    """Un profilo si conferma solo quando nessuna formula è da decidere."""
    profilo = proprio(db, utente)
    aperte = [
        n
        for n, f in enumerate(letto(profilo)["formule"], start=1)
        if f["stato"] == "da decidere"
    ]
    if aperte:
        elenco = ", ".join(map(str, aperte))
        raise StileRifiutato(
            f"Restano da decidere le formule con una norma: {elenco}."
        )
    profilo.confermato_il = adesso()
    registra_evento(db, utente, None, "conferma-stile", profilo=profilo.id)
    db.commit()
    return profilo


# [/libro:conferma-profilo]


def profilo_di(db: Session, utente: Utente, autore: Utente) -> ProfiloStile:
    """Leggere il profilo di un avvocato: avvocati e praticanti."""
    if not puo_leggere(utente):
        raise StileRifiutato("La segreteria non legge i profili dello stile.")
    profilo = ultimo_profilo(db, autore)
    if profilo is None:
        raise StileRifiutato(f"{autore.nome} non ha ancora un profilo.")
    return profilo
