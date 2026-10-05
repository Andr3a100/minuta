"""Ritrovare i precedenti dello studio nell'archivio locale.

La ricerca lavora sulle parole, con un indice a trigrammi che regge
plurali, desinenze e piccoli refusi. È tutta in locale: nessun testo
dell'archivio esce per cercare.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

# Parole che non aiutano a distinguere un atto da un altro.
VUOTE = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da",
    "in", "con", "su", "per", "tra", "fra", "e", "o", "che", "del", "della",
    "dei", "delle", "al", "alla", "nel", "nella", "non", "come", "per",
}


@dataclass
class Risultato:
    atto_id: str
    file: str
    punteggio: float
    autore: str | None
    tipo: str | None
    data: str | None
    estratto: str


def termini(domanda: str) -> list[str]:
    """Le parole utili della domanda. Numeri e date non dicono niente sul
    contenuto di un precedente: un atto pieno di «2025» non è più simile."""
    parole = re.findall(r"[\wà-ù]+", domanda.lower())
    return [p for p in parole if len(p) >= 3 and p not in VUOTE and not re.search(r"\d", p)]


def cerca(db: sqlite3.Connection, domanda: str, *, tipo: str | None = None,
          autore: str | None = None, dal: str | None = None, al: str | None = None,
          escludi: set[str] | None = None, quanti: int = 5) -> list[Risultato]:
    """I precedenti più vicini alla domanda, dal più pertinente."""
    parole = termini(domanda)
    if not parole:
        return []
    corrispondenza = " OR ".join(f'"{p}"' for p in parole)
    righe = db.execute(
        "select atto_id, bm25(indice) as costo, snippet(indice, 2, '«', '»', '…', 12) "
        "as estratto from indice where indice match ? order by costo",
        (corrispondenza,)).fetchall()
    migliori: dict[str, tuple[float, str]] = {}
    for riga in righe:
        # bm25 è un costo: più è basso, più la sezione è pertinente.
        punteggio = -riga["costo"]
        precedente = migliori.get(riga["atto_id"])
        if precedente is None:
            migliori[riga["atto_id"]] = (punteggio, riga["estratto"])
        else:
            migliori[riga["atto_id"]] = (precedente[0] + punteggio * 0.5, precedente[1])
    risultati = []
    for atto_id, (punteggio, estratto) in migliori.items():
        atto = db.execute("select * from atti where id = ?", (atto_id,)).fetchone()
        if tipo and not (atto["tipo"] or "").startswith(tipo):
            continue
        if autore and atto["autore"] != autore:
            continue
        if dal and (atto["data"] or "") < dal:
            continue
        if al and (atto["data"] or "") > al:
            continue
        if escludi and atto_id in escludi:
            continue
        risultati.append(Risultato(atto_id, atto["file"], round(punteggio, 3), atto["autore"],
                                   atto["tipo"], atto["data"], estratto))
    risultati.sort(key=lambda r: -r.punteggio)
    return risultati[:quanti]
