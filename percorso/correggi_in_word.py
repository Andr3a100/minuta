"""Lezione 26: la correzione in Word che, nella prova, fa uno script.

    python percorso/correggi_in_word.py bozza-atto.docx atto-approvato.docx

Nello studio la bozza si corregge in Word, a mano. La prova automatica non
ha mani: questo script fa le correzioni che fa Elena Sarti, sempre le
stesse, e salva il file che lei approverebbe. Toglie il riquadro e i
commenti di Minuta, completa e verifica ciò che resta da fare, riempie la
formula dello stile con i suoi dati, cancella i paragrafi sbagliati e
corregge due parole.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docx import Document  # noqa: E402

from minuta import word  # noqa: E402

# [libro:correzioni-sarti]
# I paragrafi che Elena Sarti cancella: un pagamento che nessun documento
# dice, una norma che non c'entra, una sentenza che nessuno ha letto.
CANCELLA = ("bonifico", "assegno bancario", "Cassazione")
# Ciò che completa, verifica e corregge.
CAMBIA = (
    (
        r"\[DA COMPLETARE: i motivi dell'opposizione e le loro prove\]",
        "I motivi dell'opposizione e le loro prove sono esposti di seguito.",
    ),
    (
        r"\[DA VERIFICARE\] il giudice competente per l'opposizione\.",
        "Il Tribunale di Modena è competente per l'opposizione.",
    ),
    (r"\[PERSONA\]", "Elena Sarti"),  # la formula, con i suoi dati
    (r"\[CF\]", "SRTLNE71C45F257Q"),
    (r"\[INDIRIZZO\]", "Via delle Meridiane 12"),
    (r"\[EMAIL\]", "elena.sarti@pec-avvocati.example"),
    (r"- ricorrente -", "- opponente -"),  # in un'opposizione
    (r"la somma di euro", "la sorte capitale di euro"),  # lo stile
)
# [/libro:correzioni-sarti]


def corretti(paragrafi: list[str]) -> list[str]:
    tenuti = [p for p in paragrafi if not any(c in p for c in CANCELLA)]
    for cerca, metti in CAMBIA:
        tenuti = [re.sub(cerca, metti, p) for p in tenuti]
    return tenuti


def main(bozza: str, approvato: str) -> None:
    documento = Document()  # senza riquadro, commenti né evidenziato
    for paragrafo in corretti(word.leggi(Path(bozza))):
        documento.add_paragraph(paragrafo)
    documento.save(approvato)
    print(f"Corretto come in Word: {approvato}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
