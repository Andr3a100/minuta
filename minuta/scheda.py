"""La scheda dell'atto in arrivo (lezione 18).

Il modello legge l'atto, pseudonimizzato e diviso in pagine, e propone la
scheda: righe brevi, ciascuna con la sua voce e con la pagina da cui viene.
Minuta non si fida. Controlla che ogni riga citi una pagina dell'atto, e
che ogni data e ogni importo della riga compaiano davvero in quella pagina:
ciò che non si ritrova si segnala. Quando un dato manca, la riga dice «non
risulta», come chiede la lezione 1: un vuoto non si riempie con una
supposizione.

Il controllo vede se una data c'è, non se è quella giusta. Per questo la
scheda resta da verificare: la legge l'avvocato, con la pagina accanto.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .archive import MESI

VOCI = (
    "atto",
    "parti",
    "richieste",
    "fatti",
    "prove",
    "norme",
    "importi",
    "date",
)

# [libro:istruzioni-scheda]
ISTRUZIONI = (
    "SCHEDA: leggi il documento e restituisci soltanto un oggetto JSON, "
    'senza altro testo: {"righe": [{"voce": ..., "testo": ..., '
    '"pagina": ...}]}. Le voci sono: atto, parti, richieste (o capi '
    "d'imputazione), fatti, prove, norme, importi, date. Ogni riga dice una "
    "cosa sola, con la pagina da cui viene; date e importi si scrivono come "
    "nel documento. Fra le date ci sono sempre la data dell'atto e la data "
    "della sua notificazione. Se un dato non è nel documento, la riga dice "
    "«non risulta» e la pagina è null: non dedurlo e non completarlo."
)
# [/libro:istruzioni-scheda]

MESE = "|".join(MESI)
DATA_IN_LETTERE = re.compile(
    rf"\b(\d{{1,2}})(?:°|º)?\s+({MESE})\s+(\d{{4}})\b", re.IGNORECASE
)
DATA_IN_CIFRE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
CIFRA = r"\d{1,3}(?:\.\d{3})+|\d+"
# Un importo ha i centesimi dopo la virgola, o la parola euro davanti.
CON_DECIMALI = re.compile(rf"(?<![\d.,])({CIFRA}),(\d{{2}})(?!\d)")
IN_EURO = re.compile(
    rf"(?:€|\beuro)\s*({CIFRA})(?:,(\d{{2}}))?(?!\d|[.,]\d)", re.IGNORECASE
)


class SchedaIlleggibile(ValueError):
    """La risposta del modello non è una scheda."""


@dataclass
class Riga:
    voce: str
    testo: str
    pagina: int | None
    problemi: list[str] = field(default_factory=list)
    tolta_da: str | None = None  # chi l'ha tolta dalla scheda

    @property
    def manca(self) -> bool:
        """La riga dice che il dato non è nell'atto."""
        return "non risulta" in self.testo.casefold()


def _data(anno: int, mese: int, giorno: int) -> date | None:
    try:
        return date(anno, mese, giorno)
    except ValueError:  # il 31 febbraio non esiste
        return None


def date_in(testo: str) -> set[date]:
    """Le date di un testo: «15 settembre 2026», «1° ottobre», «15/09/2026»."""
    trovate = {
        _data(int(a), MESI[m.lower()], int(g))
        for g, m, a in DATA_IN_LETTERE.findall(testo)
    }
    trovate |= {
        _data(int(a), int(m), int(g))
        for g, m, a in DATA_IN_CIFRE.findall(testo)
    }
    trovate.discard(None)
    return trovate


def importi_in(testo: str) -> set[Decimal]:
    """Gli importi di un testo: «euro 14.280,00», «6.100,00», «€ 40»."""
    trovati = set()
    for regola in (CON_DECIMALI, IN_EURO):
        for intero, centesimi in regola.findall(testo):
            cifra = intero.replace(".", "") + "." + (centesimi or "00")
            trovati.add(Decimal(cifra))
    return trovati


def in_euro(cifra: Decimal) -> str:
    """14208.00 -> «14.208,00», come si scrive in Italia."""
    return f"{cifra:,.2f}".translate(str.maketrans(",.", ".,"))


def a_pagine(pagine: list[str]) -> str:
    """Il testo dell'atto con il numero di ogni pagina: il modello lo cita."""
    return "\n\n".join(
        f"PAGINA {n}\n{testo}" for n, testo in enumerate(pagine, start=1)
    )


def leggi_risposta(testo: str) -> list[Riga]:
    """Le righe proposte dal modello, dal suo JSON. Il testo intorno, come
    i recinti ```json, si ignora; una risposta senza righe è illeggibile."""
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio < 0 or fine < inizio:
        raise SchedaIlleggibile("la risposta non contiene un oggetto JSON")
    try:
        dati = json.loads(testo[inizio : fine + 1])
    except json.JSONDecodeError as exc:
        raise SchedaIlleggibile(f"JSON non valido: {exc.msg}") from None
    righe = dati.get("righe") if isinstance(dati, dict) else None
    if not isinstance(righe, list) or not righe:
        raise SchedaIlleggibile("manca l'elenco delle righe")
    lette = []
    for riga in righe:
        if not isinstance(riga, dict):
            raise SchedaIlleggibile("una riga non è un oggetto JSON")
        pagina = riga.get("pagina")
        if isinstance(pagina, str) and pagina.strip().isdigit():
            pagina = int(pagina)
        if isinstance(pagina, bool) or not isinstance(pagina, int):
            pagina = None
        lette.append(
            Riga(
                voce=str(riga.get("voce", "")).strip().lower(),
                testo=" ".join(str(riga.get("testo", "")).split()),
                pagina=pagina,
            )
        )
    # In ordine di voce, come si legge una scheda; nella stessa voce,
    # nell'ordine del modello.
    return sorted(
        lette,
        key=lambda r: VOCI.index(r.voce) if r.voce in VOCI else len(VOCI),
    )


# [libro:controlla]
def controlla(righe: list[Riga], pagine: list[str]) -> list[Riga]:
    """Per ogni riga: la voce, la pagina, e le date e gli importi, che
    devono comparire in quella pagina. Ciò che non torna è un problema
    della riga; la riga resta, e la legge l'avvocato."""
    for riga in righe:
        if riga.voce not in VOCI:
            riga.problemi.append(f"voce sconosciuta: «{riga.voce}»")
        if riga.manca:
            continue
        if riga.pagina is None:
            riga.problemi.append("nessuna pagina: da dove viene?")
            continue
        if not 1 <= riga.pagina <= len(pagine):
            parola = "pagina" if len(pagine) == 1 else "pagine"
            riga.problemi.append(
                f"la pagina {riga.pagina} non c'è: l'atto ha "
                f"{len(pagine)} {parola}"
            )
            continue
        testo = pagine[riga.pagina - 1]
        for giorno in sorted(date_in(riga.testo) - date_in(testo)):
            riga.problemi.append(
                f"la data {giorno:%d/%m/%Y} non è a pagina {riga.pagina}"
            )
        for cifra in sorted(importi_in(riga.testo) - importi_in(testo)):
            riga.problemi.append(
                f"l'importo {in_euro(cifra)} non è a pagina {riga.pagina}"
            )
    return righe


# [/libro:controlla]
