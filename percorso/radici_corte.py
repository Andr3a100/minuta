"""Lezione 27, errore deliberato: una modifica che sembra un miglioramento.

    python percorso/radici_corte.py

Il caso del forno non passa: «forno» e «fornitura» hanno radici di cinque
lettere diverse, e la pagina del promemoria non parte. Una correzione
viene in mente subito: radici di quattro lettere. Lo script la prova senza
toccare il codice di Minuta, sostituendo per finta la funzione che riduce
le parole, e la misura con la suite di valutazione.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minuta import archivio, domande, valutazione  # noqa: E402


# [libro:radici-corte]
def parole_corte(testo: str) -> set[str]:
    """Come domande.parole, con radici di quattro lettere invece di cinque:
    «forno» e «fornitura» diventano tutte e due «forn»."""
    trovate = re.findall(r"[a-zà-ÿ]{4,}", testo.casefold())
    return {p[:4] for p in trovate if p not in domande.FERME}


# [/libro:radici-corte]


def main() -> int:
    domande.parole = archivio.parole = parole_corte  # solo in questo script
    esiti = valutazione.esegui(valutazione.carica_casi())
    righe, ok = valutazione.resoconto(esiti, valutazione.carica_riferimento())
    print("Con radici di quattro lettere, invece di cinque:")
    print("\n".join(righe))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
