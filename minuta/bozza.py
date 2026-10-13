"""La bozza: dal fascicolo, nello stile di chi firma, con la provenienza di
ogni paragrafo (lezione 24).

Due bozze: l'atto di opposizione al decreto ingiuntivo e il promemoria per
il cliente. Al modello partono i documenti del fascicolo, pseudonimizzati,
le scadenze confermate e, per l'atto, lo stile confermato dell'avvocato che
firmerà; mai gli atti di altri clienti. La bozza che torna Minuta la
controlla senza fidarsi: ogni data e ogni importo devono stare nei
documenti o nelle scadenze, ogni paragrafo dice da dove viene, i segnaposto
rimasti si segnalano, ciò che manca resta da completare.

Le citazioni si confrontano con il massimario dello studio (lezione 25):
le norme che non ci sono restano da leggere sulla fonte; una sentenza che
non c'è si segnala nel suo paragrafo, perché non si cita una sentenza che
nessuno ha letto. E se la bozza parla di qualcosa che il fascicolo non ha,
un assegno, un consumatore, una locazione, la norma che porta con sé esiste,
ma forse non c'entra.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from . import citations
from .draft import ELEMENTI
from .scadenze import in_lettere
from .scheda import date_in, importi_in, in_euro

# [libro:istruzioni-bozza]
TIPI = {
    "opposizione": (
        "BOZZA DELL'ATTO: scrivi la bozza dell'atto di opposizione al "
        "decreto ingiuntivo, per il cliente dello studio, nello STILE "
        "indicato."
    ),
    "promemoria": (
        "BOZZA DEL PROMEMORIA: scrivi al cliente dello studio una lettera in "
        "parole semplici, senza termini tecnici non spiegati, che dica che "
        "cosa è arrivato, che cosa rischia, che cosa si può fare ed entro "
        "quando. Non promettere esiti."
    ),
}
REGOLE = (
    "Usa soltanto i fatti dei DOCUMENTI e delle SCADENZE: ogni dato che "
    "manca va scritto [DA COMPLETARE: che cosa manca], senza dedurre e senza "
    "completare. Una norma di cui non sei certo va preceduta da [DA "
    "VERIFICARE]. Mantieni i segnaposto fra parentesi quadre come sono. Alla "
    "fine di ogni paragrafo scrivi da dove viene, fra parentesi graffe: "
    "{fonte: NOME DEL DOCUMENTO, pagina N}, {fonte: scadenze}, {fonte: "
    "stile}, oppure {fonte: modello} se il testo è tuo. Scrivi solo il "
    "testo, dall'intestazione alla firma: niente avvisi e niente note per "
    "l'avvocato, che aggiunge Minuta."
)
# [/libro:istruzioni-bozza]
FONTE = re.compile(r"\s*\{fonte:\s*([^}]*)\}")
# La data di una norma non è un fatto del caso: «D.P.R. 30 maggio 2002».
DATA_DI_NORMA = re.compile(
    r"(?:D\.\s?P\.\s?R\.|D\.\s?Lgs\.|R\.\s?D\.|[Ll]egge|L\.|[Dd]ecreto"
    r"(?: legislativo| ministeriale)?)\s+\d{1,2}°?\s+[a-z]+\s+\d{4}"
)
DOCUMENTO = re.compile(r"^(.+?),\s*pagina\s+(\d+)$")
SEGNAPOSTO = re.compile(r"\[[A-Z]+(?:_[A-Z]+)*(?:_\d+)?\]")
DA_COMPLETARE = re.compile(r"\[DA COMPLETARE:\s*([^\]]+)\]")
DA_VERIFICARE = re.compile(r"\[DA VERIFICARE\]\s*([^.;\n]*)")


class TipoDiBozza(LookupError):
    """Minuta non sa preparare questo tipo di bozza."""


@dataclass
class Paragrafo:
    testo: str
    fonte: str | None
    problemi: list[str] = field(default_factory=list)


def istruzioni(tipo: str) -> str:
    if tipo not in TIPI:
        raise TipoDiBozza(f"Le bozze sono: {', '.join(TIPI)}.")
    return f"{TIPI[tipo]} {REGOLE}"


def leggi_bozza(testo: str) -> list[Paragrafo]:
    """I paragrafi della bozza, ciascuno con la provenienza dichiarata."""
    paragrafi = []
    for blocco in re.split(r"\n\s*\n", testo.strip()):
        fonti = dict.fromkeys(f.strip() for f in FONTE.findall(blocco))
        pulito = FONTE.sub("", blocco).strip()
        if pulito:
            paragrafi.append(Paragrafo(pulito, "; ".join(fonti) or None))
    return paragrafi


# [libro:controlla-bozza]
def controlla(
    paragrafi: list[Paragrafo],
    documenti: dict[str, list[str]],
    scadenze: str,
) -> list[Paragrafo]:
    """Ogni paragrafo dice da dove viene; ogni data e ogni importo stanno
    nei documenti o nelle scadenze; nessun segnaposto resta."""
    tutto = "\n".join(p for pagine in documenti.values() for p in pagine)
    date_note = date_in(tutto) | date_in(scadenze)
    importi_noti = importi_in(tutto)
    for p in paragrafi:
        if p.fonte is None:
            p.problemi.append("nessuna provenienza: da dove viene?")
        for fonte in (p.fonte or "").split("; "):
            if dove := DOCUMENTO.match(fonte):
                nome, pagina = dove.group(1).strip(), int(dove.group(2))
                if not 1 <= pagina <= len(documenti.get(nome, [])):
                    fuori = f"la fonte non è nel fascicolo: {fonte}"
                    p.problemi.append(fuori)
        fatti = citations.SENTENZA.sub("", DATA_DI_NORMA.sub("", p.testo))
        for giorno in sorted(date_in(fatti) - date_note):
            p.problemi.append(
                f"data che non è nei documenti: {in_lettere(giorno)}"
            )
        for cifra in sorted(importi_in(p.testo) - importi_noti):
            p.problemi.append(
                f"importo che non è nei documenti: {in_euro(cifra)}"
            )
        for segno in dict.fromkeys(SEGNAPOSTO.findall(p.testo)):
            p.problemi.append(f"segnaposto rimasto: {segno}, da sostituire")
    return paragrafi


# [/libro:controlla-bozza]


# [libro:citazioni-bozza]
def citazioni(
    paragrafi: list[Paragrafo], massimario: citations.Massimario
) -> list[str]:
    """Le norme e le sentenze della bozza, confrontate con il massimario
    dello studio. Restituisce le norme da leggere sulla fonte; una sentenza
    che il massimario non ha si segnala nel suo paragrafo."""
    da_leggere = []
    for p in paragrafi:
        for c in citations.estrai(p.testo):
            if massimario.stato(c) == "verificata":
                continue
            if c.tipo == "sentenza":
                p.problemi.append(
                    f"sentenza che il massimario non ha: «{c.testo}»; non "
                    "si cita una sentenza che nessuno ha letto"
                )
            else:
                da_leggere.append(c.chiave)
    return list(dict.fromkeys(da_leggere))


def pertinenza(
    paragrafi: list[Paragrafo], documenti: dict[str, list[str]]
) -> None:
    """Gli elementi che cambiano la natura del caso: se la bozza ne parla e
    i documenti no, la norma che li accompagna esiste, ma forse non
    c'entra."""
    tutto = "\n".join(p for pagine in documenti.values() for p in pagine)
    for elemento, regola in ELEMENTI.items():
        if re.search(regola, tutto, re.IGNORECASE):
            continue
        for p in paragrafi:
            if re.search(regola, p.testo, re.IGNORECASE):
                p.problemi.append(
                    f"parla di {elemento}, che il fascicolo non ha: la norma "
                    "esiste, ma c'entra?"
                )


# [/libro:citazioni-bozza]


def da_completare(paragrafi: list[Paragrafo]) -> list[str]:
    return [m for p in paragrafi for m in DA_COMPLETARE.findall(p.testo)]


def da_verificare(paragrafi: list[Paragrafo]) -> list[str]:
    return [
        m.strip() or "una norma"
        for p in paragrafi
        for m in DA_VERIFICARE.findall(p.testo)
    ]


def manca_la_scadenza(
    paragrafi: list[Paragrafo], scadenze: list[date]
) -> bool:
    """Un promemoria che non dice entro quando non è un promemoria."""
    scritte = set().union(*(date_in(p.testo) for p in paragrafi))
    return bool(scadenze) and not set(scadenze) & scritte


def in_markdown(
    intestazione: str, paragrafi: list[Paragrafo], note: list[str]
) -> str:
    """La bozza come la legge il modulo Word (minuta/word.py): testo,
    provenienza, note per l'avvocato."""
    righe = [f"> {intestazione}", ""]
    for p in paragrafi:
        righe += [p.testo, ""]
        if p.fonte:
            righe += [f"<sub>provenienza: {p.fonte}</sub>", ""]
    righe += ["---", "", "## Note per l'avvocato", ""]
    righe += [f"- {n}" for n in note] or ["- Nessun avviso."]
    return "\n".join(righe) + "\n"
