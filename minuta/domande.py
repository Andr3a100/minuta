"""Le domande sul fascicolo: la pagina, o «non c'è» (lezione 21).

Prima di chiedere, Minuta sceglie da sola i passi dei documenti che parlano
della domanda: le pagine che ne contengono le parole. Partono solo quelli,
pseudonimizzati. Se nessun passo ne parla, non parte niente, e la risposta
è che nel fascicolo non c'è.

Il modello risponde con frasi brevi, ciascuna con il documento, la pagina e
le parole esatte da cui viene. Minuta controlla che ogni citazione stia
davvero a quella pagina di quel documento, fra quelli mandati; ciò che non
si ritrova si segnala. Una citazione esatta prova che le parole ci sono,
non che dicano ciò che la frase dice: la risposta la legge l'avvocato.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# [libro:istruzioni-domanda]
ISTRUZIONI = (
    "DOMANDA SUL FASCICOLO: rispondi solo con i passi qui sotto, e "
    'restituisci soltanto un oggetto JSON: {"frasi": [{"testo": ..., '
    '"documento": ..., "pagina": ..., "citazione": ...}]}. Ogni frase dice '
    "una cosa sola; la citazione riporta le parole esatte del passo da cui "
    "viene, senza cambiarle. Se i passi non rispondono alla domanda, "
    'restituisci {"frasi": [], "non_c_e": "..."} e scrivi che cosa manca: '
    "non dedurre e non completare."
)
# [/libro:istruzioni-domanda]

FERME = frozenset(
    """
    alla alle allo dalla dalle dallo della delle dello degli nella nelle
    nello negli sulla sulle sullo sugli come dopo prima quale quali quando
    quanto questo questa questi queste quello quella quelli quelle essere
    sono hanno fatto anche ancora entro oppure perché dove cosa cose
    """.split()
)
MASSIMO_PASSI = 3


@dataclass
class Passo:
    documento: str
    pagina: int
    testo: str
    punti: int = 0


@dataclass
class Frase:
    testo: str
    documento: str
    pagina: int | None
    citazione: str
    problemi: list[str] = field(default_factory=list)


def parole(testo: str) -> set[str]:
    """Le parole che contano, ridotte alla radice: «notificato» e
    «notificazione» diventano «notif»."""
    trovate = re.findall(r"[a-zà-ÿ]{4,}", testo.casefold())
    return {p[:5] for p in trovate if p not in FERME}


# [libro:scegli]
def scegli_passi(domanda: str, documenti: dict[str, list[str]]) -> list:
    """Le pagine che contengono più parole della domanda, al massimo tre,
    in ordine di documento e di pagina. Nessuna, se nessuna ne parla."""
    cercate = parole(domanda)
    candidati = []
    for nome, pagine in documenti.items():
        for numero, testo in enumerate(pagine, start=1):
            punti = len(cercate & parole(testo))
            if punti:
                candidati.append(Passo(nome, numero, testo, punti))
    migliori = sorted(candidati, key=lambda p: -p.punti)[:MASSIMO_PASSI]
    ordine = list(documenti)
    return sorted(
        migliori, key=lambda p: (ordine.index(p.documento), p.pagina)
    )


# [/libro:scegli]


def a_passi(passi: list[Passo]) -> str:
    return "\n\n".join(
        f"DOCUMENTO: {p.documento} · PAGINA {p.pagina}\n{p.testo}"
        for p in passi
    )


class RispostaIlleggibile(ValueError):
    """La risposta del modello non è nella forma chiesta."""


def leggi_risposta(testo: str) -> tuple[list[Frase], str | None]:
    """Le frasi con le loro citazioni, oppure che cosa manca."""
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio < 0 or fine < inizio:
        raise RispostaIlleggibile("la risposta non contiene un oggetto JSON")
    try:
        dati = json.loads(testo[inizio : fine + 1])
    except json.JSONDecodeError as exc:
        raise RispostaIlleggibile(f"JSON non valido: {exc.msg}") from None
    frasi = dati.get("frasi") if isinstance(dati, dict) else None
    if not isinstance(frasi, list):
        raise RispostaIlleggibile("manca l'elenco delle frasi")
    manca = dati.get("non_c_e") or None
    if not frasi and not manca:
        raise RispostaIlleggibile("nessuna frase, e nessun «non c'è»")
    lette = []
    for f in frasi:
        if not isinstance(f, dict):
            raise RispostaIlleggibile("una frase non è un oggetto JSON")
        pagina = f.get("pagina")
        if isinstance(pagina, str) and pagina.strip().isdigit():
            pagina = int(pagina)
        if isinstance(pagina, bool) or not isinstance(pagina, int):
            pagina = None
        lette.append(
            Frase(
                testo=" ".join(str(f.get("testo", "")).split()),
                documento=str(f.get("documento", "")).strip(),
                pagina=pagina,
                citazione=" ".join(str(f.get("citazione", "")).split()),
            )
        )
    return lette, manca


def normale(testo: str) -> str:
    """Per confrontare una citazione: minuscole, spazi e a capo uniti,
    apostrofi e virgolette di un tipo solo."""
    testo = testo.casefold().translate(str.maketrans("’‘“”«»", '\'\'""""'))
    return " ".join(testo.split())


# [libro:controlla-citazioni]
def controlla(frasi: list[Frase], passi: list[Passo]) -> list[Frase]:
    """Ogni citazione deve stare, parola per parola, alla pagina citata di
    un passo mandato al modello."""
    mandati = {(p.documento, p.pagina): p.testo for p in passi}
    for frase in frasi:
        testo = mandati.get((frase.documento, frase.pagina))
        if testo is None:
            frase.problemi.append(
                f"{frase.documento}, pagina {frase.pagina}: "
                "non è fra i passi mandati"
            )
        elif not frase.citazione:
            frase.problemi.append("nessuna citazione: da dove viene?")
        elif normale(frase.citazione) not in normale(testo):
            frase.problemi.append(
                f"la citazione non è a pagina {frase.pagina} "
                f"di {frase.documento}"
            )
    return frasi


# [/libro:controlla-citazioni]
