"""I tipi di atto (lezione 40): configurazione, non codice.

Un tipo di atto in arrivo è una dichiarazione in config/tipi/, che mette
insieme quattro cose già scritte altrove: le domande di verifica
(config/verifiche.json), la regola del termine (config/termini.json), le
bozze di risposta (config/bozze.json) e un documento di prova, su cui il
tipo si prova prima di usarlo su un fascicolo vero. Per insegnare a Minuta
un tipo nuovo non si tocca il codice: si scrivono questi file, e questo
modulo dice se il tipo è completo.

Una regola con una parte «da verificare» è completa: Minuta, quando quella
parte serve, si ferma e lo dice (lezione 19). Una norma senza la fonte o
senza la data di lettura, invece, non è una regola.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
CARTELLA = RADICE / "config" / "tipi"


@dataclass
class Esame:
    nome: str
    righe: list[tuple[str, bool, str]] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        return all(ok for _, ok, _ in self.righe)


def carica_tipi(cartella: Path = CARTELLA) -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(cartella.glob("*.json"))
    ]


def letta(voce: dict) -> bool:
    return bool(voce.get("fonte")) and bool(voce.get("letta_il"))


# [libro:tipo]
def esamina(
    tipo: dict, domande: dict, regole: dict, bozze: dict, radice: Path = RADICE
) -> Esame:
    """Le quattro parti di un tipo di atto, ciascuna con il suo esito."""
    esame = Esame(tipo["nome"])
    elenco = domande["tipi"].get(tipo["domande"])
    if elenco is None:
        esame.righe.append(("domande", False, "mancano in verifiche.json"))
    elif any("norma" in d and not letta(d) for d in elenco):
        esame.righe.append(("domande", False, "una norma senza fonte o data"))
    else:
        con_norma = sum("norma" in d for d in elenco)
        esame.righe.append(
            ("domande", True, f"{len(elenco)}, {con_norma} con la norma letta")
        )
    trovate = [r for r in regole["termini"] if r["nome"] == tipo["termine"]]
    if not trovate:
        esame.righe.append(("termine", False, "manca in termini.json"))
    elif not all(letta(r) and r.get("norma") for r in trovate):
        esame.righe.append(("termine", False, "una norma senza fonte o data"))
    else:
        aperte = sorted(
            {k for r in trovate for k, v in r.items() if v == "da verificare"}
        )
        norme = "; ".join(
            f"{r['norma']}, letta il {r['letta_il']}" for r in trovate
        )
        dettaglio = norme + (
            f"; da verificare: {', '.join(aperte)}" if aperte else ""
        )
        esame.righe.append(("termine", True, dettaglio))
    mancano = [b for b in tipo["bozze"] if b not in bozze]
    if mancano:
        dettaglio = f"mancano in bozze.json: {', '.join(mancano)}"
        esame.righe.append(("bozze", False, dettaglio))
    else:
        esame.righe.append(("bozze", True, ", ".join(tipo["bozze"])))
    prova = radice / tipo["prova"]
    esame.righe.append(
        (
            "prova",
            prova.is_file(),
            tipo["prova"] if prova.is_file() else "manca",
        )
    )
    return esame


# [/libro:tipo]
