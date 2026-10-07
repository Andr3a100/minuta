"""La prova delle fughe: niente di riconoscibile deve lasciare lo studio.

Si esegue su ogni testo prima che parta verso il fornitore del modello. Se
trova qualcosa, l'invio non avviene.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .pseudonym import CODICE_FISCALE, EMAIL, IBAN

PARTITA_IVA_NUDA = re.compile(r"\b\d{11}\b")


def fughe(testo: str, sensibili: Iterable[str] = ()) -> list[str]:
    """I dati sensibili ancora presenti nel testo, vuota se è pulito."""
    trovate = []
    minuscolo = testo.lower()
    for valore in sensibili:
        schema = r"\s+".join(re.escape(p) for p in valore.lower().split())
        if schema and re.search(rf"(?<![\w]){schema}(?![\w])", minuscolo):
            trovate.append(valore)
    for regola, tipo in ((CODICE_FISCALE, "codice fiscale"), (IBAN, "IBAN"),
                         (EMAIL, "indirizzo email"), (PARTITA_IVA_NUDA, "partita IVA")):
        trovate += [f"{tipo}: {m.group(0)}" for m in regola.finditer(testo)]
    return trovate
