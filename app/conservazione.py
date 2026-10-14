"""Quanto si conservano i fascicoli, e come si cancellano (lezione 33).

Quanto conservare lo decide lo studio, con il motivo e la data, in
config/conservazione.json; Minuta lo applica. Il conto parte dal giorno in
cui il fascicolo è stato chiuso, scritto nel registro delle attività: se
il fascicolo si riapre, la chiusura che conta è l'ultima. Dove la regola
dice «da decidere», Minuta non cancella niente.

Cancellare un fascicolo vuol dire togliere tutto ciò che Minuta ne
conserva: le righe di ogni tabella, i suoi eventi, gli originali dei
documenti nella cartella dei dati. Un originale si toglie soltanto se
nessun altro fascicolo ha lo stesso documento, perché gli originali si
conservano per impronta. Restano le voci del registro dell'uso dell'AI,
che non contengono testi, senza il fascicolo, e una riga che dice chi ha
cancellato che cosa. Il fascicolo resta nelle copie di sicurezza fino a
quando le copie si tolgono: Minuta lo dice, con la data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from minuta.scadenze import MESI

from .config import Settings
from .copie import fascicoli_nelle_copie
from .db import (
    Assegnazione,
    Bozza,
    Correzione,
    Documento,
    Evento,
    Fascicolo,
    PersonaFascicolo,
    RispostaFascicolo,
    Scadenza,
    Scheda,
    Segnaposto,
    UsoAI,
    Utente,
    Verifica,
    adesso,
)
from .documenti import cartella_dati
from .rules import passaggio_ammesso, passaggio_previsto
from .web import registra_evento

REGOLA = Path(__file__).resolve().parents[1] / "config" / "conservazione.json"


class ConservazioneRifiutata(Exception):
    """Il passaggio o la cancellazione non si fa: il messaggio dice perché."""


@dataclass
class Chiuso:
    codice: str
    cliente: str
    chiuso_il: date
    fino_al: date | None


@dataclass
class Residui:
    file_senza_documento: list[str]
    documenti_senza_file: list[str]
    nelle_copie: list[tuple[str, int, date]]


def carica_regola(percorso: Path | None = None) -> dict:
    return json.loads((percorso or REGOLA).read_text(encoding="utf-8"))


def data_in_lettere(giorno: date) -> str:
    numero = "1°" if giorno.day == 1 else str(giorno.day)
    return f"{numero} {MESI[giorno.month - 1]} {giorno.year}"


def passa_di_stato(
    db: Session, utente: Utente, fascicolo: Fascicolo, nuovo: str
) -> str:
    """Il passaggio di stato dal terminale, con le regole della pagina
    del fascicolo (lezione 15) e la sua riga nel registro."""
    prima = fascicolo.stato
    if not passaggio_previsto(prima, nuovo):
        raise ConservazioneRifiutata(
            f"Da «{prima}» a «{nuovo}»: passaggio non previsto."
        )
    if not passaggio_ammesso(prima, nuovo, utente.ruolo):
        raise ConservazioneRifiutata("Il tuo ruolo non consente il passaggio.")
    fascicolo.stato = nuovo
    fascicolo.versione += 1
    fascicolo.aggiornato_il = adesso()
    registra_evento(db, utente, fascicolo, "stato", prima=prima, dopo=nuovo)
    db.commit()
    return prima


def chiuso_il(db: Session, fascicolo: Fascicolo) -> date | None:
    """Il giorno dell'ultima chiusura, dal registro delle attività."""
    if fascicolo.stato != "chiuso":
        return None
    # Il fascicolo è chiuso: l'ultimo passaggio di stato è la chiusura.
    ultimo = db.scalar(
        select(Evento)
        .where(Evento.fascicolo_id == fascicolo.id, Evento.azione == "stato")
        .order_by(Evento.id.desc())
        .limit(1)
    )
    return (ultimo or fascicolo).creato_il.date()


def fino_al(chiusura: date, regola: dict) -> date | None:
    """Il giorno da cui il fascicolo si può cancellare; None, se lo
    studio non ha ancora deciso."""
    anni = regola["fascicoli"]["anni"]
    if not isinstance(anni, int):
        return None
    try:
        return chiusura.replace(year=chiusura.year + anni)
    except ValueError:  # il 29 febbraio, in un anno che non ce l'ha
        return chiusura.replace(year=chiusura.year + anni, day=28)


def fascicoli_chiusi(db: Session, regola: dict) -> list[Chiuso]:
    chiusi = []
    for f in db.scalars(
        select(Fascicolo)
        .where(Fascicolo.stato == "chiuso")
        .order_by(Fascicolo.codice)
    ):
        giorno = chiuso_il(db, f)
        chiusi.append(
            Chiuso(f.codice, f.cliente, giorno, fino_al(giorno, regola))
        )
    return chiusi


# [libro:cancella]
def cancella_fascicolo(
    db: Session,
    settings: Settings,
    utente: Utente,
    fascicolo: Fascicolo,
    regola: dict,
    oggi: date,
) -> list[str]:
    """Toglie il fascicolo, in tutte le tabelle e nella cartella dei dati,
    quando la regola dello studio lo consente; lo decide il suo avvocato.
    Restituisce gli originali tolti."""
    if utente.id != fascicolo.avvocato_id:
        raise ConservazioneRifiutata(
            "Un fascicolo lo cancella il suo avvocato."
        )
    giorno = chiuso_il(db, fascicolo)
    if giorno is None:
        raise ConservazioneRifiutata(f"{fascicolo.codice} non è chiuso.")
    dal = fino_al(giorno, regola)
    if dal is None:
        raise ConservazioneRifiutata(
            "Lo studio non ha deciso quanto conservare i fascicoli."
        )
    if oggi < dal:
        raise ConservazioneRifiutata(
            f"{fascicolo.codice} si conserva: si cancella dal "
            f"{data_in_lettere(dal)}."
        )
    f = fascicolo.id
    documenti = db.scalars(
        select(Documento).where(Documento.fascicolo_id == f)
    )
    impronte = {d.impronta for d in documenti}
    altrove = set(
        db.scalars(
            select(Documento.impronta).where(
                Documento.impronta.in_(impronte), Documento.fascicolo_id != f
            )
        )
    )
    for tabella in (
        Correzione,
        Scadenza,
        Verifica,
        Scheda,
        Bozza,
        RispostaFascicolo,
        Segnaposto,
        PersonaFascicolo,
        Documento,
        Assegnazione,
        Evento,
    ):  # prima le righe che rimandano ad altre righe del fascicolo
        db.execute(delete(tabella).where(tabella.fascicolo_id == f))
    db.execute(
        update(UsoAI).where(UsoAI.fascicolo_id == f).values(fascicolo_id=None)
    )
    db.delete(fascicolo)
    registra_evento(
        db,
        utente,
        None,
        "cancellazione",
        codice=fascicolo.codice,
        chiuso_il=giorno.isoformat(),
        documenti=len(impronte),
    )
    db.commit()  # le righe, insieme o per niente; poi i file
    tolti = []
    for impronta in sorted(impronte - altrove):
        originale = cartella_dati(settings) / "documenti" / impronta
        originale.unlink(missing_ok=True)
        tolti.append(impronta)
    return tolti


# [/libro:cancella]


def residui(db: Session, settings: Settings, regola: dict) -> Residui:
    """Ciò che resta fuori posto: originali che nessun documento usa,
    documenti senza originale, fascicoli cancellati ancora nelle copie."""
    cartella = cartella_dati(settings) / "documenti"
    sul_disco = (
        {p.name for p in cartella.iterdir() if p.is_file()}
        if cartella.is_dir()
        else set()
    )
    usate = set(db.scalars(select(Documento.impronta)))
    esistenti = set(db.scalars(select(Fascicolo.codice)))
    copie = fascicoli_nelle_copie(
        Path(settings.copie_dir), regola["copie"]["giorni"]
    )
    nelle_copie = [
        (codice, len(scadenze), max(scadenze))
        for codice, scadenze in sorted(copie.items())
        if codice not in esistenti
    ]
    return Residui(
        sorted(sul_disco - usate), sorted(usate - sul_disco), nelle_copie
    )
