"""La misura dopo l'avvio (lezione 38): la misura di partenza della
lezione 2, rifatta con Minuta nel lavoro dello studio.

I minuti non li misura Minuta: li cronometra chi lavora, e li registra
con il comando `tempo`, come riga del registro delle attività del
fascicolo. Il resto Minuta lo sa già: se la scadenza è stata calcolata con
la sua norma e confermata da un avvocato, e se l'avvocato, approvando una
bozza, ha corretto un dato. Il confronto con la misura di partenza si fa
soltanto con almeno tanti fascicoli quanti ne aveva quella: con meno, i
numeri si mostrano e il verdetto no.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.misure import quota, riassunto

from .db import Bozza, Evento, Fascicolo, Scadenza, Utente
from .web import registra_evento

PARTENZA = (
    Path(__file__).resolve().parents[1] / "config" / "misura-di-partenza.json"
)
ATTIVITA = ("studio", "stesura", "rilettura")


class MisuraRifiutata(Exception):
    """Il tempo non si registra: il messaggio dice perché."""


@dataclass
class Misura:
    fascicoli: list[str]
    minuti: dict[str, list[int]]
    documentate: int
    con_errori: int


def carica_partenza(percorso: Path | None = None) -> dict:
    return json.loads((percorso or PARTENZA).read_text(encoding="utf-8"))


def registra_tempo(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    attivita: str,
    minuti: int,
) -> None:
    """I minuti cronometrati da chi ha lavorato al fascicolo."""
    if attivita not in ATTIVITA:
        raise MisuraRifiutata(f"Le attività sono: {', '.join(ATTIVITA)}.")
    if not 1 <= minuti <= 1440:
        raise MisuraRifiutata("I minuti vanno da 1 a 1440.")
    registra_evento(
        db, utente, fascicolo, "tempo", attivita=attivita, minuti=minuti
    )
    db.commit()


# [libro:misura]
def misura_di_oggi(db: Session) -> Misura:
    """I fascicoli con i minuti di studio registrati: i minuti di ogni
    attività, quanti hanno la scadenza confermata, quanti una bozza in
    cui l'avvocato ha corretto un dato."""
    per_fascicolo: dict[int, dict[str, int]] = {}
    for evento in db.scalars(select(Evento).where(Evento.azione == "tempo")):
        d = json.loads(evento.dettaglio)
        minuti = per_fascicolo.setdefault(evento.fascicolo_id, {})
        minuti[d["attivita"]] = minuti.get(d["attivita"], 0) + d["minuti"]
    misurati = [f for f, m in per_fascicolo.items() if "studio" in m]
    codici, documentate, con_errori = [], 0, 0
    for fascicolo in db.scalars(
        select(Fascicolo)
        .where(Fascicolo.id.in_(misurati))
        .order_by(Fascicolo.codice)
    ):
        codici.append(fascicolo.codice)
        documentate += bool(
            db.scalar(
                select(Scadenza.id).where(
                    Scadenza.fascicolo_id == fascicolo.id,
                    Scadenza.confermata_da_id.isnot(None),
                )
            )
        )
        con_errori += any(
            json.loads(b.modifiche or "{}").get("dati", 0) > 0
            for b in db.scalars(
                select(Bozza).where(Bozza.fascicolo_id == fascicolo.id)
            )
        )
    minuti = {
        a: [per_fascicolo[f][a] for f in misurati if a in per_fascicolo[f]]
        for a in ATTIVITA
    }
    return Misura(codici, minuti, documentate, con_errori)


def verdetto(partenza: dict, oggi: Misura) -> list[str]:
    """L'obiettivo della lezione 2, indicatore per indicatore. Con meno
    fascicoli della misura di partenza, nessun verdetto."""
    servono = len(partenza["studio"])
    n = len(oggi.fascicoli)
    if n < servono:
        attesa = f"la misura di partenza ne ha {servono}"
        return [
            f"Fascicoli misurati: {n}; {attesa}. Nessun confronto, ancora."
        ]
    obiettivo = partenza["obiettivo"]
    _media, mediana = riassunto(oggi.minuti["studio"])
    prima = quota(
        sum(1 for e in partenza["errori_in_revisione"] if e), servono
    )
    dopo = quota(oggi.con_errori, n)
    righe = [
        (
            "tempo mediano di studio",
            mediana < obiettivo["studio_mediana_sotto"],
        ),
        ("scadenze documentate", quota(oggi.documentate, n) >= 100),
        ("errori in revisione non cresciuti", dopo <= prima),
    ]
    esito = [f"{nome}: {'sì' if ok else 'no'}" for nome, ok in righe]
    raggiunto = all(ok for _, ok in righe)
    esito.append(
        "Obiettivo raggiunto."
        if raggiunto
        else "Obiettivo non raggiunto: vale la condizione di riesame "
        "(lezione 2)."
    )
    return esito


# [/libro:misura]
