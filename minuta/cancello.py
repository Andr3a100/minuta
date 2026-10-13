"""Il cancello di una modifica (lezione 29): ciò che si controlla prima che
una modifica di Minuta, scritta da una persona o da un agente, diventi una
versione.

La modifica, com'è nei commit, si confronta con la versione da cui
parte. Le prove le esegue la prova automatica, sui tre sistemi; il
cancello guarda ciò che le prove non vedono: se la modifica ha cambiato la
misura invece di Minuta. I casi che c'erano non si toccano; il
riferimento non perde casi e non ne peggiora; la suite, misurata contro il
riferimento della versione di partenza, non peggiora. Le asserzioni tolte
dalle prove e le dipendenze cambiate non fermano la modifica: si leggono,
una per una.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from . import valutazione

DIPENDENZE = ("requirements.txt", "requirements-test.txt")


@dataclass
class Esame:
    base: str
    file: list[str]
    risposte_cambiate: list[str]
    riferimento_peggiorato: list[str]
    peggiorati: list[str]
    migliorati: list[str]
    asserzioni_tolte: list[str] = field(default_factory=list)
    dipendenze: list[str] = field(default_factory=list)

    @property
    def passa(self) -> bool:
        return not (
            self.risposte_cambiate
            or self.riferimento_peggiorato
            or self.peggiorati
        )


def _git(*argomenti: str) -> str:
    return subprocess.run(
        ["git", *argomenti],
        cwd=valutazione.RADICE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def alla_base(base: str, percorso: str) -> str:
    return _git("show", f"{base}:{percorso}")


# [libro:cancello]
def risposte_cambiate(prima: list[dict], dopo: list[dict]) -> list[str]:
    """I casi che c'erano e che non ci sono più, o che sono cambiati: la
    domanda, i documenti, la risposta. Soltanto la nota si può riscrivere.
    Una modifica cambia Minuta, non la misura."""
    adesso = {c["id"]: c for c in dopo}
    cambiati = []
    for caso in prima:
        nuovo = adesso.get(caso["id"])
        if nuovo is None:
            cambiati.append(f"{caso['id']}: tolto")
            continue
        for campo in sorted((set(caso) | set(nuovo)) - {"nota"}):
            if caso.get(campo) != nuovo.get(campo):
                cambiati.append(f"{caso['id']}: {campo}")
    return cambiati


def riferimento_peggiorato(
    prima: dict[str, bool], dopo: dict[str, bool]
) -> list[str]:
    """I casi che passavano e che il nuovo riferimento toglie o dà per
    falliti: accettare un peggioramento non è una modifica di Minuta."""
    return [id_ for id_, ok in prima.items() if ok and not dopo.get(id_)]


# [/libro:cancello]


def asserzioni_tolte(base: str) -> list[str]:
    """Le righe con un assert tolte o cambiate nelle prove: da leggere."""
    tolte = []
    for riga in _git("diff", "-U0", base, "HEAD", "--", "tests").splitlines():
        if riga.startswith("--- a/"):
            file = riga[6:]
        elif riga.startswith("-") and "assert" in riga:
            tolte.append(f"{file}: {riga[1:].strip()}")
    return tolte


def esamina(base: str) -> Esame:
    file = _git("diff", "--name-only", base, "HEAD").split()
    casi_prima = json.loads(alla_base(base, "valutazione/casi.json"))["casi"]
    riferimento_prima = json.loads(
        alla_base(base, "valutazione/riferimento.json")
    )
    esiti = valutazione.esegui(valutazione.carica_casi())
    peggiorati, migliorati = valutazione.confronta(esiti, riferimento_prima)
    return Esame(
        base=base,
        file=file,
        risposte_cambiate=risposte_cambiate(
            casi_prima, valutazione.carica_casi()
        ),
        riferimento_peggiorato=riferimento_peggiorato(
            riferimento_prima, valutazione.carica_riferimento()
        ),
        peggiorati=[e.id for e in peggiorati],
        migliorati=[e.id for e in migliorati],
        asserzioni_tolte=asserzioni_tolte(base),
        dipendenze=[f for f in file if f in DIPENDENZE],
    )


def resoconto(esame: Esame) -> list[str]:
    cambiati = f"{len(esame.file)} file cambiati"
    righe = [f"Il cancello, rispetto a {esame.base}: {cambiati}."]
    for titolo, elenco in (
        ("Casi cambiati", esame.risposte_cambiate),
        ("Riferimento: casi tolti o peggiorati", esame.riferimento_peggiorato),
        ("La suite peggiora", esame.peggiorati),
    ):
        if elenco:
            righe.append(f"{titolo}: {len(elenco)}.")
            righe += [f"  {e}" for e in elenco]
        else:
            righe.append(f"{titolo}: nessuno.")
    if esame.migliorati:
        righe.append(f"La suite migliora: {', '.join(esame.migliorati)}.")
    for titolo, elenco in (
        ("Asserzioni tolte o cambiate, da leggere", esame.asserzioni_tolte),
        ("Dipendenze cambiate, da leggere", esame.dipendenze),
    ):
        if elenco:
            righe.append(f"{titolo}: {len(elenco)}.")
            righe += [f"  {e}" for e in elenco]
    if esame.passa:
        righe.append(
            "Il cancello è aperto: la modifica può diventare una versione, "
            "dopo che una persona l'ha letta."
        )
    else:
        righe.append("Il cancello è chiuso: la modifica non entra in uso.")
    return righe
