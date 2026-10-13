"""Lezione 28, errore deliberato: un insieme di addestramento con i soli
nomi tolti.

    python percorso/solo_nomi.py

Per il profilo dello stile (lezione 23) bastava togliere i nomi: Minuta ne
conta le formule, e i fatti restano dove sono. Lo script prepara gli atti
di Elena Sarti allo stesso modo, come se fossero pronti per addestrare un
modello, e conta che cosa dei suoi clienti un modello imparerebbe. Legge
gli atti di prova dell'archivio e non scrive niente.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minuta import documenti  # noqa: E402
from minuta.addestramento import fatti_rimasti, senza_fatti  # noqa: E402
from minuta.archivio import etichetta, leggi_indice, tipo_del_nome  # noqa: E402
from minuta.stile import generico  # noqa: E402

ARCHIVIO = Path(__file__).resolve().parents[1] / "archivio"
STUDIO = {"Elena Sarti": "PERSONA", "Marco Dini": "PERSONA"}


def main() -> None:
    indice = leggi_indice(ARCHIVIO / "indice.csv")
    print("Gli atti di Elena Sarti con i soli nomi tolti, come per lo stile:")
    totale = dopo = 0
    for pdf in sorted((ARCHIVIO / "pdf").glob("*-sarti-*.pdf")):
        testo = documenti.leggi(pdf.name, pdf.read_bytes()).testo
        persone = {n: tipo_del_nome(n) for n in indice[pdf.stem]}
        senza_nomi = generico(testo, STUDIO | persone)
        fatti = fatti_rimasti(senza_nomi)
        totale += len(fatti)
        dopo += len(fatti_rimasti(senza_fatti(senza_nomi)))
        print(
            f"{etichetta(int(pdf.name[:2]))}  {len(fatti):>2} fatti, per "
            f"esempio {fatti[0]}"
        )
    print(f"Fatti dei clienti che un modello imparerebbe: {totale}.")
    print(f"Con anche i fatti tolti, come fa Minuta: {dopo}.")


if __name__ == "__main__":
    main()
