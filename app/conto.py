"""Il conto dello studio (lezione 36), rifatto con ciò che si è misurato.

La lezione 3 ha fatto il conto con numeri simulati. Costruendo Minuta se ne
sono misurati alcuni: quanto costa davvero una richiesta di ogni tipo al
modello del fornitore (le chiamate vere dei verbali, in config/conto.json),
e quante richieste di ogni tipo partono per un fascicolo (il registro
dell'uso dell'AI). Gli altri restano simulati, e il conto lo dice accanto a
ogni numero: il tempo di chi rilegge, soprattutto, si misura soltanto
quando lo studio usa Minuta (lezione 38).

Il registro conta anche le richieste al modello finto, che non costano
niente e non hanno un prezzo: per questo il riepilogo dei costi della
lezione 31 dice zero. Qui ogni richiesta prende il prezzo misurato del suo
tipo; un tipo senza prezzo misurato resta fuori, e si vede.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.conti import anno_di_pareggio, ore, saldi

from .db import Fascicolo, UsoAI

CONTO = Path(__file__).resolve().parents[1] / "config" / "conto.json"


@dataclass
class Stima:
    codice: str
    richieste: int
    dollari: float
    senza_prezzo: list[str] = field(default_factory=list)


def carica_conto(percorso: Path | None = None) -> dict:
    return json.loads((percorso or CONTO).read_text(encoding="utf-8"))


def prezzi_misurati(conto: dict) -> dict[str, tuple[float, int]]:
    """Per ogni tipo di richiesta, la mediana delle chiamate vere e quante
    sono: una chiamata sola è un prezzo, non una media."""
    per_scopo: dict[str, list[float]] = {}
    for chiamata in conto["chiamate_vere"]:
        per_scopo.setdefault(chiamata["scopo"], []).append(chiamata["dollari"])
    return {s: (median(v), len(v)) for s, v in sorted(per_scopo.items())}


# [libro:stima]
def stima_per_fascicolo(db: Session, prezzi: dict) -> list[Stima]:
    """Le richieste di ogni fascicolo nel registro, ciascuna al prezzo
    misurato del suo tipo, qualunque modello abbia risposto."""
    stime = []
    for fascicolo in db.scalars(select(Fascicolo).order_by(Fascicolo.codice)):
        scopi = Counter(
            db.scalars(
                select(UsoAI.scopo).where(UsoAI.fascicolo_id == fascicolo.id)
            )
        )
        dollari = sum(
            prezzi[s][0] * n for s, n in scopi.items() if s in prezzi
        )
        stime.append(
            Stima(
                fascicolo.codice,
                sum(scopi.values()),
                round(dollari, 4),
                sorted(s for s in scopi if s not in prezzi),
            )
        )
    return stime


# [/libro:stima]


def ritorno(ipotesi: dict, anni: int = 5) -> tuple[list[float], int | None]:
    """Il ritorno prudente della lezione 3, con le ipotesi di oggi: metà
    delle ore nette liberate, al costo orario."""
    v = {nome: voce["valore"] for nome, voce in ipotesi.items()}
    nette = ore(v["fascicoli al mese"], v["minuti risparmiati"]) - ore(
        v["fascicoli al mese"], v["minuti di rilettura"]
    )
    beneficio = nette * v["costo orario"] * 12 / 2
    elenco = saldi(v["avvio"], v["gestione annua"], beneficio, anni)
    return elenco, anno_di_pareggio(elenco)
