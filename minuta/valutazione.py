"""La suite di valutazione (lezione 27): casi con la risposta nota.

Ogni caso dice che cosa Minuta deve fare su un documento di prova, una
domanda o una data: quali pagine mandare e quali no, e quando nessuna;
quale atto dell'archivio mettere per primo; quando scade un termine, o che
decide l'avvocato; se le somme di una pagina tornano; quali citazioni ci
sono in un testo; quale errore noto del modello finto la scheda segnala.
Nessun caso chiama un modello vero: la suite misura Minuta, non il
fornitore, e costa niente.

I risultati accettati stanno in un riferimento. Una modifica di Minuta può
far passare un caso che prima non passava; non può farne fallire uno che
passava. I casi che non passano si sanno, e restano scritti.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from . import archivio, citations, documenti, domande, scheda, verifiche
from .model import ModelloFinto
from .scadenze import calcola, carica_regole

RADICE = Path(__file__).resolve().parents[1]
CASI = RADICE / "valutazione" / "casi.json"
RIFERIMENTO = RADICE / "valutazione" / "riferimento.json"
TIPI = ("passi", "archivio", "scadenza", "somme", "citazioni", "scheda")


@dataclass
class Esito:
    id: str
    tipo: str
    superato: bool
    detto: str  # che cosa ha fatto Minuta, in una riga


@cache
def pagine_del_fascicolo(codice: str) -> dict[str, list[str]]:
    """Le pagine dei documenti di prova di un fascicolo, lette da Minuta."""
    cartella = RADICE / "documenti-di-prova" / codice
    return {
        f.name: [
            p.testo for p in documenti.leggi(f.name, f.read_bytes()).pagine
        ]
        for f in sorted(cartella.iterdir())
    }


@cache
def atti_dell_archivio() -> tuple[archivio.AttoLetto, ...]:
    atti = []
    for pdf in sorted((RADICE / "archivio" / "pdf").glob("*.pdf")):
        letto = documenti.leggi(pdf.name, pdf.read_bytes())
        atti.append(
            archivio.AttoLetto(
                int(pdf.name[:2]),
                "",
                "",
                None,
                [p.testo for p in letto.pagine],
            )
        )
    return tuple(atti)


def _passi(caso: dict) -> Esito:
    scelti = domande.scegli_passi(
        caso["domanda"], pagine_del_fascicolo(caso["fascicolo"])
    )
    partiti = [p.documento for p in scelti]
    attesi = caso["attesi"]
    # Le pagine che non parlano della domanda non partono: se nessuna ne
    # parla, nessuna; altrimenti quelle che il caso esclude (lezione 21).
    esclusi = caso.get("esclusi", []) if attesi else partiti
    superato = set(attesi) <= set(partiti) and not set(esclusi) & set(partiti)
    detto = ", ".join(partiti) if partiti else "nessuna pagina"
    return Esito(caso["id"], "passi", superato, f"partono: {detto}")


def _archivio(caso: dict) -> Esito:
    trovati = archivio.cerca(caso["domanda"], list(atti_dell_archivio()))
    primo = (
        archivio.etichetta(trovati[0].atto.numero) if trovati else "nessuno"
    )
    atteso = archivio.etichetta(int(caso["atteso"]))
    return Esito(caso["id"], "archivio", primo == atteso, f"primo: {primo}")


def _scadenza(caso: dict) -> Esito:
    esito = calcola(
        caso["termine"], date.fromisoformat(caso["partenza"]), carica_regole()
    )
    trovata = esito.scadenza.isoformat() if esito.scadenza else "da decidere"
    return Esito(
        caso["id"], "scadenza", trovata == caso["attesa"], f"scade: {trovata}"
    )


def _somme(caso: dict) -> Esito:
    pagine = pagine_del_fascicolo(caso["fascicolo"])[caso["documento"]]
    tornano = [
        ok for pagina in pagine for ok, _ in verifiche.controlla_somme(pagina)
    ]
    detto = ", ".join("torna" if ok else "non torna" for ok in tornano)
    return Esito(
        caso["id"],
        "somme",
        tornano == caso["attese"],
        f"totali: {detto or 'nessuno'}",
    )


def _citazioni(caso: dict) -> Esito:
    trovate = [c.chiave for c in citations.estrai(caso["testo"])]
    return Esito(
        caso["id"],
        "citazioni",
        trovate == caso["attese"],
        f"trovate: {', '.join(trovate) or 'nessuna'}",
    )


def _scheda(caso: dict) -> Esito:
    """La scheda del modello finto, che sbaglia sempre allo stesso modo:
    l'errore noto deve essere segnalato, e nient'altro."""
    pagine = pagine_del_fascicolo(caso["fascicolo"])[caso["documento"]]
    risposta = ModelloFinto().scrivi(
        scheda.ISTRUZIONI, f"{scheda.ISTRUZIONI}\n\n{scheda.a_pagine(pagine)}"
    )
    righe = scheda.controlla(scheda.leggi_risposta(risposta.testo), pagine)
    segnalate = sorted({r.voce for r in righe if r.problemi})
    return Esito(
        caso["id"],
        "scheda",
        segnalate == sorted(caso["segnalate"]),
        f"segnalate: {', '.join(segnalate) or 'nessuna'}",
    )


MISURE = {
    "passi": _passi,
    "archivio": _archivio,
    "scadenza": _scadenza,
    "somme": _somme,
    "citazioni": _citazioni,
    "scheda": _scheda,
}


def carica_casi(percorso: Path = CASI) -> list[dict]:
    return json.loads(percorso.read_text("utf-8"))["casi"]


def esegui(casi: list[dict]) -> list[Esito]:
    return [MISURE[caso["tipo"]](caso) for caso in casi]


def carica_riferimento(percorso: Path | None = None) -> dict[str, bool]:
    percorso = percorso or RIFERIMENTO
    return json.loads(percorso.read_text("utf-8")) if percorso.exists() else {}


# [libro:confronta]
def confronta(
    esiti: list[Esito], riferimento: dict[str, bool]
) -> tuple[list[Esito], list[Esito]]:
    """Rispetto ai risultati accettati: i casi peggiorati, che passavano e
    ora no, e quelli migliorati. Un caso nuovo che non passa conta come
    peggiorato: un caso si aggiunge con la sua risposta, non per far
    numero."""
    peggiorati = [
        e for e in esiti if not e.superato and riferimento.get(e.id, True)
    ]
    migliorati = [
        e for e in esiti if e.superato and riferimento.get(e.id) is False
    ]
    return peggiorati, migliorati


# [/libro:confronta]


def accetta(esiti: list[Esito], percorso: Path | None = None) -> None:
    """I risultati di oggi diventano il riferimento: una decisione, che il
    commit del laboratorio conserva."""
    (percorso or RIFERIMENTO).write_text(
        json.dumps({e.id: e.superato for e in esiti}, indent=2) + "\n", "utf-8"
    )


def resoconto(
    esiti: list[Esito], riferimento: dict[str, bool]
) -> tuple[list[str], bool]:
    """Le righe che la suite stampa, e se la modifica può entrare in uso."""
    righe = [f"La suite di valutazione: {len(esiti)} casi."]
    for tipo in TIPI:
        del_tipo = [e for e in esiti if e.tipo == tipo]
        if del_tipo:
            passati = sum(e.superato for e in del_tipo)
            righe.append(f"{tipo:<11} {passati:>2} su {len(del_tipo)}")
    falliti = [e for e in esiti if not e.superato]
    if falliti:
        righe.append("Non passano:")
        righe += [f"  {e.id} · {e.detto}" for e in falliti]
    peggiorati, migliorati = confronta(esiti, riferimento)
    for nome, gruppo in (
        ("migliorati", migliorati),
        ("peggiorati", peggiorati),
    ):
        if gruppo:
            righe.append(f"Rispetto al riferimento, {nome}: {len(gruppo)}.")
            righe += [f"  {e.id}" for e in gruppo]
    if not peggiorati:
        righe.append("Nessun caso peggiorato: la modifica può entrare in uso.")
    else:
        righe.append("La modifica non entra in uso.")
    return righe, not peggiorati
