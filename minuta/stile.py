"""Lo stile di ogni avvocato, ricavato dagli atti che ha firmato (lezione 23).

Senza nessun modello: Minuta conta. Prende gli atti dell'archivio di un
avvocato, con i nomi nascosti da segnaposto senza numero ([SOGGETTO],
[PERSONA]), e ne ricava come comincia un suo ricorso, quanto sono lunghe le
sue frasi e le formule che tornano in almeno due atti, ciascuna con gli
atti da cui viene. Una formula con una norma può non essere stile, ma una
scelta di diritto: giusta in un caso, sbagliata in un altro. Minuta la
segnala, con gli atti dell'avvocato in cui manca, e la decide l'avvocato.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

from .pseudonym import Pseudonimizzatore

TOKEN = re.compile(r"\[[A-Z_]+\]|[\wà-ÿ'’]+")
# Le parole vere, di almeno tre lettere: segnaposto e sigle non contano.
PAROLA = re.compile(r"(?<!\[)\b[a-zà-ÿ'’]{3,}\b", re.IGNORECASE)
NORMA = re.compile(
    r"\bartt?\.|\bD\.\s?Lgs\.|\bD\.P\.R\.|\bc\.p\.c\.|\bc\.c\.|"
    r"\blegge\s+(?:n\.\s*)?\d|\bL\.\s?\d",
    re.IGNORECASE,
)
# Una frase finisce con il punto, il punto e virgola o i due punti, se dopo
# viene una maiuscola e se prima non c'è un'abbreviazione: «n.», «art.».
FINE_FRASE = re.compile(r"(?<=[.;:])\s+(?=[A-ZÀ-Ý0-9])")
ABBREVIAZIONI = re.compile(
    r"\b(?:n|artt?|Avv|sig|dott|Ill\.mo|D\.Lgs|D\.P\.R|C\.F|P\.\s?IVA)\.$",
    re.IGNORECASE,
)
VUOTE = frozenset(
    "a al alla da dal dalla del della di e il in la le lo per".split()
)
LUNGHEZZA = 6  # parole di fila: con meno, due atti si somigliano per caso
MASSIMO = 12  # le formule di stile del profilo, dalle più diffuse


@dataclass
class Formula:
    testo: str
    atti: list[int]
    manca: list[int]  # gli atti dell'avvocato in cui non c'è
    norma: bool
    stato: str  # «stile», oppure «da decidere» se contiene una norma


@dataclass
class Profilo:
    atti: list[int]
    intestazione: str | None
    titolo: str | None
    parole_per_frase: float
    formule: list[Formula]


def generico(testo: str, noti: dict[str, str]) -> str:
    """Il testo con segnaposto senza numero: lo stile resta, i nomi no.
    Le legature dei PDF tornano lettere: «ﬁ» diventa «fi»."""
    testo = unicodedata.normalize("NFKC", testo)
    return Pseudonimizzatore(generico=True, noti=dict(noti)).nascondi(testo)


def frasi(testo: str) -> list[str]:
    testo = " ".join(testo.split())
    pezzi, inizio = [], 0
    for m in FINE_FRASE.finditer(testo):
        if not ABBREVIAZIONI.search(testo[inizio : m.start()]):
            pezzi.append(testo[inizio : m.start()])
            inizio = m.end()
    pezzi.append(testo[inizio:])
    return [p for p in pezzi if p]


def ripulita(frase: str) -> str:
    """Senza le preposizioni e gli articoli rimasti ai bordi: «al saldo,
    oltre spese e compensi del» diventa «saldo, oltre spese e compensi»."""
    parole = frase.split(" ")
    while parole and parole[-1].casefold() in VUOTE:
        parole.pop()
    while parole and parole[0].casefold() in VUOTE:
        parole.pop(0)
    return " ".join(parole).strip(" ,")


def ripetute(testi: dict[int, str]) -> dict[str, list[int]]:
    """I tratti di almeno sei parole che tornano in due o più atti, come
    sono scritti nel primo di quegli atti, frase per frase."""
    parole = {n: list(TOKEN.finditer(t)) for n, t in testi.items()}
    dove = defaultdict(set)
    for n, trovate in parole.items():
        chiavi = [m.group(0).casefold() for m in trovate]
        for i in range(len(chiavi) - LUNGHEZZA + 1):
            dove[tuple(chiavi[i : i + LUNGHEZZA])].add(n)
    # Le finestre consecutive con gli stessi atti diventano un tratto solo.
    per_atti = defaultdict(set)
    for finestra, atti in dove.items():
        if len(atti) >= 2:
            per_atti[tuple(sorted(atti))].add(finestra)
    trovate = {}
    for atti, finestre in per_atti.items():
        primo = parole[atti[0]]
        chiavi = [m.group(0).casefold() for m in primo]
        inizio = fine = None
        for i in range(len(chiavi) - LUNGHEZZA + 2):
            dentro = tuple(chiavi[i : i + LUNGHEZZA]) in finestre
            if dentro and inizio is not None and i <= fine:
                fine = i + LUNGHEZZA
            elif dentro:
                inizio, fine = i, i + LUNGHEZZA
            if inizio is not None and (not dentro or i == len(chiavi)):
                tratto = testi[atti[0]][
                    primo[inizio].start() : primo[fine - 1].end()
                ]
                for frase in map(ripulita, frasi(tratto)):
                    if len(PAROLA.findall(frase)) >= LUNGHEZZA:
                        trovate.setdefault(frase, list(atti))
                inizio = None
    # Una formula dentro un'altra, dagli stessi atti o da meno, è già lì.
    return {
        f: a
        for f, a in trovate.items()
        if not any(
            f != g and f in g and set(a) <= set(b) for g, b in trovate.items()
        )
    }


# [libro:calcola-stile]
def calcola(atti: dict[int, tuple[str | None, str]]) -> Profilo:
    """Il profilo di un avvocato dai suoi atti: numero -> (tipo, testo con
    i segnaposto senza numero)."""
    ricorsi = [
        t for tipo, t in atti.values() if (tipo or "").startswith("ric")
    ]
    righe = [[r for r in t.splitlines() if r.strip()] for t in ricorsi]
    tutte = [f for _, t in atti.values() for f in frasi(t)]
    parole = sum(len(TOKEN.findall(f)) for f in tutte) / max(len(tutte), 1)
    formule = []
    for testo, dove in ripetute({n: t for n, (_, t) in atti.items()}).items():
        norma = bool(NORMA.search(testo))
        manca = sorted(set(atti) - set(dove))
        stato = "da decidere" if norma else "stile"
        formule.append(Formula(testo, dove, manca, norma, stato))
    formule.sort(key=lambda f: (-len(f.atti), -len(f.testo)))
    # Le formule con una norma ci sono tutte: vanno decise, non contate.
    stile = [f for f in formule if not f.norma][:MASSIMO]
    norme = [f for f in formule if f.norma]
    return Profilo(
        atti=sorted(atti),
        intestazione=_piu_comune(r[0] for r in righe if r),
        titolo=_piu_comune(r[1] for r in righe if len(r) > 1),
        parole_per_frase=round(parole, 1),
        formule=stile + norme,
    )


# [/libro:calcola-stile]


def _piu_comune(valori) -> str | None:
    conteggio = Counter(valori)
    return conteggio.most_common(1)[0][0] if conteggio else None
