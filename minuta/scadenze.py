"""Le scadenze: calcolarle, non indovinarle (lezione 19).

Il modello trova soltanto il punto di partenza: la data della notificazione,
nella scheda dell'atto che un avvocato ha confermato (lezione 18). Il resto
lo fa Minuta, con le regole scritte in config/termini.json: quanti giorni,
da quando, come si contano, quali giorni sono festivi, quando il tempo si
ferma. Ogni regola porta la norma letta sulla fonte ufficiale, e ogni
passaggio del calcolo la cita.

Dove le regole non bastano, o una regola è ancora da verificare, Minuta non
sceglie: lo dice, e decide l'avvocato.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

REGOLE = Path(__file__).resolve().parents[1] / "config" / "termini.json"
SETTIMANA = "lunedì martedì mercoledì giovedì venerdì sabato domenica".split()
MESI = (
    "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre "
    "ottobre novembre dicembre"
).split()


class TermineSconosciuto(LookupError):
    """Nessuna regola per quel termine, a quella data."""


@dataclass
class Calcolo:
    termine: str
    norma: str
    partenza: date
    scadenza: date | None = None  # None: decide l'avvocato
    passaggi: list[str] = field(default_factory=list)
    da_decidere: str | None = None


def carica_regole(percorso: Path = REGOLE) -> dict:
    return json.loads(percorso.read_text("utf-8"))


def in_lettere(giorno: date) -> str:
    """lunedì 2 novembre 2026; il primo del mese è «1°»."""
    numero = "1°" if giorno.day == 1 else str(giorno.day)
    mese = MESI[giorno.month - 1]
    return f"{SETTIMANA[giorno.weekday()]} {numero} {mese} {giorno.year}"


def pasqua(anno: int) -> date:
    """La domenica di Pasqua del calendario gregoriano (algoritmo di
    Meeus): serve per il lunedì dopo Pasqua."""
    a, (b, c) = anno % 19, divmod(anno, 100)
    d, e = divmod(b, 4)
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    elle = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * elle) // 451
    mese, giorno = divmod(h + elle - 7 * m + 114, 31)
    return date(anno, mese, giorno + 1)


def festivo(giorno: date, festivi: dict) -> str | None:
    """Il nome della festa, se il giorno è festivo; altrimenti None."""
    chiave = f"{giorno:%m-%d}"
    if giorno.year >= festivi["dal_anno"].get(chiave, 0):
        if chiave in festivi["fissi"]:
            return festivi["fissi"][chiave]
    dopo_pasqua = pasqua(giorno.year) + timedelta(days=1)
    if festivi["lunedi_dopo_pasqua"] and giorno == dopo_pasqua:
        return "lunedì dopo Pasqua"
    if festivi["domeniche"] and giorno.weekday() == 6:
        return "domenica"
    return None


def regola_del_termine(regole: dict, nome: str, partenza: date) -> dict:
    """La regola del termine in vigore alla data di partenza. Basta l'inizio
    del nome, se indica un termine solo: «ricorso», «opposizione»."""
    nomi = {r["nome"] for r in regole["termini"]}
    if nome not in nomi:
        simili = sorted(n for n in nomi if n.startswith(nome.casefold()))
        if len(simili) > 1:
            raise TermineSconosciuto(
                f"«{nome}» indica più termini: {'; '.join(simili)}."
            )
        nome = simili[0] if simili else nome
    for regola in regole["termini"]:
        if regola["nome"] != nome:
            continue
        if "dal" in regola and partenza < date.fromisoformat(regola["dal"]):
            continue
        if "fino_al" in regola and partenza > date.fromisoformat(
            regola["fino_al"]
        ):
            continue
        return regola
    raise TermineSconosciuto(
        f"Nessuna regola per «{nome}» alla data {partenza:%d/%m/%Y}."
    )


def in_ferie(giorno: date, ferie: dict) -> bool:
    return ferie["dal"] <= f"{giorno:%m-%d}" <= ferie["al"]


# [libro:calcola]
def calcola(nome: str, partenza: date, regole: dict) -> Calcolo:
    """La scadenza del termine, passaggio per passaggio, ciascuno con la
    sua norma; oppure il motivo per cui decide l'avvocato."""
    regola = regola_del_termine(regole, nome, partenza)
    computo = regole["computo"][regola["computo"]]
    ferie = regole["sospensione_feriale"]
    sospeso = regola["sospensione_feriale"]
    esito = Calcolo(regola["nome"], regola["norma"], partenza)
    esito.passaggi.append(
        f"{regola['giorni']} giorni dalla {regola['da']}: {regola['norma']}, "
        f"letta il {regola['letta_il']}"
    )
    if regola.get("rinvio") == "da verificare":
        esito.da_decidere = (
            f"per {regola['norma']} il rinvio al codice di procedura civile, "
            "che dice come si contano i giorni, è da verificare"
        )
        return esito
    esito.passaggi.append(
        f"partenza {in_lettere(partenza)}, che non si conta "
        f"({computo['norma']})"
    )
    giorno, contati, fermi = partenza, 0, 0
    while contati < regola["giorni"]:
        giorno += timedelta(days=1)
        if in_ferie(giorno, ferie) and sospeso == "da verificare":
            esito.da_decidere = (
                "il termine attraversa agosto, e per questa materia la "
                "sospensione feriale è da verificare"
            )
            return esito
        if in_ferie(giorno, ferie) and sospeso == "si":
            fermi += 1
            continue
        contati += 1
    if fermi:
        esito.passaggi.append(
            f"{fermi} giorni di agosto non si contano ({ferie['norma']})"
        )
    esito.passaggi.append(f"il {contati}° giorno è {in_lettere(giorno)}")
    while motivo := festivo(giorno, regole["festivi"]) or (
        "sabato" if computo["sabato"] and giorno.weekday() == 5 else None
    ):
        giorno += timedelta(days=1)
        esito.passaggi.append(
            f"è {motivo}: la scadenza passa a {in_lettere(giorno)} "
            f"({computo['norma']})"
        )
        if in_ferie(giorno, ferie) and sospeso == "si":
            esito.da_decidere = (
                "la proroga porta la scadenza in agosto, e le norme lette non "
                "dicono se la sospensione feriale vale anche per la proroga"
            )
            return esito
    esito.scadenza = giorno
    return esito


# [/libro:calcola]
