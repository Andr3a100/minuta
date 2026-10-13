"""Lezione 29, errore deliberato: una modifica che fa passare un caso
cambiando la sua risposta.

    python percorso/modifica_che_bara.py

Chiesto di far passare il caso del forno, un agente può scegliere la
strada corta: scrivere come risposta attesa le pagine che Minuta manda
già, e segnare il caso come superato nel riferimento. Lo script fa questa
modifica in una cartella temporanea, senza il glossario della versione
1.2, e la mostra prima alla suite e poi al cancello. Il laboratorio non
viene toccato.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minuta import cancello, valutazione  # noqa: E402

BASE = "v1.1.2"


def main() -> int:
    casi_prima = json.loads(cancello.alla_base(BASE, "valutazione/casi.json"))
    riferimento_prima = json.loads(
        cancello.alla_base(BASE, "valutazione/riferimento.json")
    )
    # [libro:la-strada-corta]
    casi = json.loads(json.dumps(casi_prima))
    for caso in casi["casi"]:
        if caso["id"] == "passi-forno":  # le pagine che partono già
            caso["attesi"] = ["fattura-112.xml.p7m", "ricorso.pdf"]
    riferimento = {**riferimento_prima, "passi-forno": True}
    # [/libro:la-strada-corta]
    with tempfile.TemporaryDirectory() as cartella:
        percorsi = {
            "CASI": Path(cartella, "casi.json"),
            "RIFERIMENTO": Path(cartella, "riferimento.json"),
            "GLOSSARI": Path(cartella, "glossari.json"),
        }
        percorsi["CASI"].write_text(json.dumps(casi), "utf-8")
        percorsi["RIFERIMENTO"].write_text(json.dumps(riferimento), "utf-8")
        percorsi["GLOSSARI"].write_text("{}", "utf-8")  # niente glossario
        originali = {nome: getattr(valutazione, nome) for nome in percorsi}
        for nome, percorso in percorsi.items():
            setattr(valutazione, nome, percorso)
        try:
            esiti = valutazione.esegui(valutazione.carica_casi())
        finally:
            for nome, percorso in originali.items():
                setattr(valutazione, nome, percorso)
        peggiorati, migliorati = valutazione.confronta(esiti, riferimento)
        print("La suite, da sola, con il riferimento della modifica:")
        superati = sum(e.superato for e in esiti)
        print(f"  casi superati: {superati} su {len(esiti)}")
        print(f"  peggiorati: {len(peggiorati)}")
        esame = cancello.Esame(
            base=BASE,
            file=["valutazione/casi.json", "valutazione/riferimento.json"],
            risposte_cambiate=cancello.risposte_cambiate(
                casi_prima["casi"], casi["casi"]
            ),
            riferimento_peggiorato=cancello.riferimento_peggiorato(
                riferimento_prima, riferimento
            ),
            peggiorati=[e.id for e in peggiorati],
            migliorati=[e.id for e in migliorati],
        )
    print("\n".join(cancello.resoconto(esame)))
    return 0 if esame.passa else 1


if __name__ == "__main__":
    sys.exit(main())
