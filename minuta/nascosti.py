"""Il testo che un PDF contiene ma che chi lo legge non vede.

Un atto può contenere frasi in bianco, in corpo minuscolo o fuori dalla
pagina: a schermo non si vedono, ma un programma che estrae il testo le
trova, e un modello le leggerebbe come il resto. Minuta le cerca e le mostra
all'avvocato, senza cancellarle: se qualcuno le ha messe lì, sono anche una
prova.

Il bianco è segnalato sempre, anche se su uno sfondo scuro sarebbe
visibile: decide l'avvocato, guardando la pagina.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

BIANCO = 0xFFFFFF
CORPO_MINIMO = 2.0  # in punti tipografici


@dataclass
class Nascosto:
    pagina: int
    testo: str
    motivo: str


def testo_nascosto(percorso: Path) -> list[Nascosto]:
    """Le righe di testo invisibili a chi legge, pagina per pagina."""
    with pymupdf.open(percorso) as documento:
        return nel_documento(documento)


def nel_documento(documento: pymupdf.Document) -> list[Nascosto]:
    """Come testo_nascosto, su un PDF già aperto (lezione 16)."""
    trovati = []
    for numero, pagina in enumerate(documento, start=1):
        # Senza ritaglio: anche il testo fuori dalla pagina, che il lettore
        # del pilota (archive.leggi_pdf) non estrae ma altri programmi sì.
        for blocco in pagina.get_text("dict", clip=pymupdf.INFINITE_RECT())["blocks"]:
            for riga in blocco.get("lines", []):
                pezzi, motivi = [], []
                for span in riga["spans"]:
                    if not span["text"].strip():
                        continue
                    perche = []
                    if span["color"] == BIANCO:
                        perche.append("testo bianco")
                    if span["size"] < CORPO_MINIMO:
                        perche.append("corpo minuscolo")
                    if not pagina.rect.intersects(pymupdf.Rect(span["bbox"])):
                        perche.append("fuori dalla pagina")
                    if perche:
                        pezzi.append(span["text"].strip())
                        motivi += [m for m in perche if m not in motivi]
                if not pezzi:
                    continue
                motivo = ", ".join(motivi)
                # Le righe consecutive con lo stesso motivo sono una frase sola.
                ultimo = trovati[-1] if trovati else None
                if ultimo and ultimo.pagina == numero and ultimo.motivo == motivo:
                    ultimo.testo += " " + " ".join(pezzi)
                else:
                    trovati.append(Nascosto(numero, " ".join(pezzi), motivo))
    return trovati
