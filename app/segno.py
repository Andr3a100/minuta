"""Il segno dei testi generati (lezione 34).

L'art. 50, par. 2, del regolamento europeo sull'intelligenza artificiale
chiede ai fornitori dei sistemi che generano testi di marcarne gli output
«in un formato leggibile meccanicamente». Studio Meridiana, che ha messo
Minuta in servizio con il proprio nome, ne è il fornitore. La bozza in
Word lo diceva già alle persone, in testa alla prima pagina (lezione 24);
da questa versione lo dice anche ai programmi, nelle proprietà del file,
che Word mostra in «Informazioni» e che un programma legge senza aprire il
testo.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document

from . import __version__

PAROLA = "generato-con-IA"


# [libro:segna]
def segna(percorso: Path, modello: str) -> None:
    """Le proprietà del file Word dicono che il testo è generato."""
    documento = Document(str(percorso))
    proprieta = documento.core_properties
    proprieta.keywords = PAROLA
    proprieta.category = "Bozza generata da un sistema di IA"
    proprieta.comments = (
        f"Testo generato da Minuta {__version__}, sistema di IA dello studio, "
        f"con il modello {modello}. Bozza da rivedere: non è un atto."
    )
    documento.save(str(percorso))


# [/libro:segna]


def leggi_segno(percorso: Path) -> list[str]:
    """Il segno, come lo legge un programma; vuoto, se non c'è."""
    proprieta = Document(str(percorso)).core_properties
    if PAROLA not in (proprieta.keywords or ""):
        return []
    return [
        f"Parole chiave: {proprieta.keywords}",
        f"Categoria: {proprieta.category}",
        f"Commenti: {proprieta.comments}",
    ]
