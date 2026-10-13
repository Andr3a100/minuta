"""La bozza: dal fascicolo, nello stile di chi firma, con la provenienza di
ogni paragrafo (lezione 24).

Due bozze: l'atto di opposizione al decreto ingiuntivo e il promemoria per
il cliente. Al modello partono i documenti del fascicolo, pseudonimizzati,
le scadenze confermate e, per l'atto, lo stile confermato dell'avvocato che
firmerà; mai gli atti di altri clienti. La bozza che torna Minuta la
controlla senza fidarsi: ogni data e ogni importo devono stare nei
documenti o nelle scadenze, ogni paragrafo dice da dove viene, i segnaposto
rimasti si segnalano, ciò che manca resta da completare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

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
        fatti = DATA_DI_NORMA.sub("", p.testo)
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
