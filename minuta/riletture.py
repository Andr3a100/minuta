"""La qualità nel tempo (lezione 33): ciò che invecchia nei file di config.

Le regole di Minuta portano la data in cui le abbiamo lette, e alcune la
data da cui valgono o fino a cui valgono. La suite di valutazione misura
Minuta, che non cambia da sola; ciò che cambia nel tempo sono le norme, i
listini, i contratti. Questo modulo cerca, in ogni file, le voci lette da
più di un certo numero di mesi e quelle che cominciano o smettono di
valere nei prossimi mesi, con ciò che hanno ancora «da verificare».
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

LETTURE = ("letta_il", "letto_il")


@dataclass
class Voce:
    file: str
    nome: str
    quando: date
    che_cosa: str  # «letta», «dal» o «fino_al»
    da_verificare: list[str] = field(default_factory=list)


def tra_mesi(giorno: date, mesi: int) -> date:
    anno, mese = divmod(giorno.month - 1 + mesi, 12)
    try:
        return giorno.replace(year=giorno.year + anno, month=mese + 1)
    except ValueError:  # il 31, in un mese più corto
        return giorno.replace(year=giorno.year + anno, month=mese + 1, day=28)


def come_data(valore) -> date | None:
    """Una data intera; None per ciò che non lo è, come il «08-01» della
    sospensione feriale, che torna ogni anno."""
    try:
        return date.fromisoformat(valore) if isinstance(valore, str) else None
    except ValueError:
        return None


def nome_di(nodo: dict, percorso: str) -> str:
    for chiave in ("nome", "norma", "voce"):
        if isinstance(nodo.get(chiave), str):
            testo = nodo[chiave]
            if chiave == "nome" and isinstance(nodo.get("norma"), str):
                testo += f", {nodo['norma']}"
            return testo
    return percorso or "tutto il file"


def nodi(dati, percorso: str = ""):
    """Ogni dizionario del file, con il suo percorso."""
    if isinstance(dati, dict):
        yield percorso, dati
        for chiave, valore in dati.items():
            yield from nodi(valore, f"{percorso}.{chiave}".lstrip("."))
    elif isinstance(dati, list):
        for n, valore in enumerate(dati):
            yield from nodi(valore, f"{percorso}[{n}]")


# [libro:riletture]
def da_rileggere(file: str, dati, oggi: date, mesi: int = 6) -> list[Voce]:
    """Le voci lette da più di `mesi` mesi, e quelle che cominciano o
    smettono di valere entro `mesi` mesi, con le loro parti da verificare."""
    voci = []
    for percorso, nodo in nodi(dati):
        nome = nome_di(nodo, percorso)
        aperte = sorted(k for k, v in nodo.items() if v == "da verificare")
        for chiave in LETTURE:
            letta = come_data(nodo.get(chiave))
            if letta and tra_mesi(letta, mesi) <= oggi:
                voci.append(Voce(file, nome, letta, "letta"))
        for chiave in ("dal", "fino_al"):
            giorno = come_data(nodo.get(chiave))
            if giorno and oggi <= giorno <= tra_mesi(oggi, mesi):
                voci.append(Voce(file, nome, giorno, chiave, aperte))
    return voci


# [/libro:riletture]


def della_cartella(cartella: Path, oggi: date, mesi: int = 6) -> list[Voce]:
    voci = []
    for percorso in sorted(cartella.glob("*.json")):
        dati = json.loads(percorso.read_text(encoding="utf-8"))
        voci += da_rileggere(percorso.name, dati, oggi, mesi)
    return sorted(voci, key=lambda v: (v.quando, v.file, v.nome))
