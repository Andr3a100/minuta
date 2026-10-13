"""Gli scritti dello studio, pronti per un addestramento in locale
(lezione 28).

L'addestramento si fa soltanto su un modello che gira nello studio, e il
suo risultato resta dello studio. Prima di addestrare, gli atti
dell'archivio diventano un insieme di testi da cui imparare la forma, mai
i fatti. Togliere i nomi bastava al profilo dello stile, che delle frasi
conta soltanto le formule; non basta a un modello addestrato, che impara
anche le fatture, gli importi e le date di un cliente, e può riscriverli
nell'atto di un altro. Qui importi, date, anni e numeri dei documenti
diventano segnaposto; le norme restano come sono, perché sono diritto, non
fatti.
"""

from __future__ import annotations

import re

from .scheda import (
    CON_DECIMALI,
    DATA_IN_CIFRE,
    DATA_IN_LETTERE,
    IN_EURO,
    date_in,
    importi_in,
    in_euro,
)

# Le norme citate con i loro numeri: «D.Lgs. 9 ottobre 2002, n. 231»,
# «D.P.R. 115/2002», «legge n. 132/2025».
NORMA = re.compile(
    r"(?:D\.\s?P\.\s?R\.|D\.\s?Lgs\.|R\.\s?D\.|[Ll]egge|L\.|[Dd]ecreto"
    r"(?: legislativo| ministeriale)?|DM|DPR)\s+"
    r"(?:\d{1,2}°?\s+[a-z]+\s+\d{4}(?:,?\s*n\.\s*\d+)?"  # con la data
    r"|(?:n\.\s*)?\d+(?:/\d{4})?)"  # con il solo numero
)
NUMERO = re.compile(r"\bn\.\s*\d+(?:/\d{2,4})?")
ANNO = re.compile(r"\b(?:19|20)\d{2}\b")


def _norme(testo: str) -> tuple[str, list[str]]:
    """Le norme messe da parte, perché nessuna regola le tocchi."""
    messe = []

    def metti(trovata: re.Match) -> str:
        messe.append(trovata.group(0))
        return f"\x00{len(messe) - 1}\x00"

    testo = NORMA.sub(metti, testo)
    return testo, messe


def _rimetti(testo: str, messe: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: messe[int(m.group(1))], testo)


# [libro:senza-fatti]
def senza_fatti(testo: str) -> str:
    """Il testo di un atto, già senza nomi, anche senza i fatti del suo
    cliente: importi, date, anni e numeri dei documenti. Le norme
    restano."""
    testo, norme = _norme(testo)
    for regola, segnaposto in (
        (IN_EURO, "euro [IMPORTO]"),
        (CON_DECIMALI, "[IMPORTO]"),
        (DATA_IN_LETTERE, "[DATA]"),
        (DATA_IN_CIFRE, "[DATA]"),
        (NUMERO, "n. [NUMERO]"),
        (ANNO, "[ANNO]"),
    ):
        testo = regola.sub(segnaposto, testo)
    return _rimetti(testo, norme)


def fatti_rimasti(testo: str) -> list[str]:
    """Ciò che di un cliente resta in un testo: un insieme di
    addestramento con anche un solo fatto non si scrive."""
    fuori_dalle_norme = _norme(testo)[0]
    date = [f"data {d:%d/%m/%Y}" for d in sorted(date_in(fuori_dalle_norme))]
    importi = [
        f"importo {in_euro(i)}" for i in sorted(importi_in(fuori_dalle_norme))
    ]
    return date + importi


# [/libro:senza-fatti]
