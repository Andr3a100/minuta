"""Che cosa parte verso il modello, e che cosa resta nello studio (lezione 17).

Prima di ogni invio il testo passa da tre controlli. I nomi dell'elenco
delle persone del fascicolo e gli identificativi diventano segnaposto
(minuta/pseudonym.py), e la tabella che li ricollega ai valori veri resta
nello studio. La prova delle fughe cerca quei valori nel testo che
partirebbe (minuta/leaks.py). La ricerca dei nomi rimasti segnala le parole
che sembrano un nome di persona e che nessuno ha messo in elenco: è il caso
della lezione 4, il dipendente ferito che il pilota lasciava passare. Se una
delle ultime due ricerche trova qualcosa, l'invio non parte.

I dati sulla salute non bloccano: si segnalano, perché se servono alla
domanda lo decide l'avvocato.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

from .leaks import fughe
from .pseudonym import Pseudonimizzatore

COMUNI = Path(__file__).resolve().parents[1] / "config" / "comuni.txt"

# Le istruzioni che accompagnano ogni testo pseudonimizzato.
SISTEMA = (
    "Rispondi in italiano. Nel testo i nomi delle persone e dei soggetti, e "
    "i loro dati, sono sostituiti da segnaposto come [PERSONA_1] o "
    "[SOGGETTO_1]: usali così come sono, senza cercare di indovinare chi "
    "siano."
)

# Due o tre parole di seguito, sulla stessa riga, con l'iniziale maiuscola.
NOME_PROPRIO = re.compile(
    r"\b[A-ZÀ-Ý][a-zà-ÿ'’]+(?:[ \t]+[A-ZÀ-Ý][a-zà-ÿ'’]+){1,2}\b"
)
# Le parole con la maiuscola che non sono nomi di persona: inizi di frase,
# istituzioni, titoli, mesi e giorni.
FERME = frozenset(
    """
    Il La Lo Le Gli I Un Una Uno Per Con Nel Nella Nei Nelle Negli Dal Dalla
    Dai Dalle Della Delle Dei Degli Del Sul Sulla Sui In A Da Di E Ed Ma Se
    Che Questo Questa Quello Quella Si Non Al Alla Ai Alle Allo Tutto Tutti
    Ogni Visto Visti Vista Viste Considerato Premesso Ritenuto Letto Fatto
    Tribunale Procura Repubblica Corte Cassazione Giustizia Codice Stato
    Agenzia Entrate Riscossione Direzione Ministero Consiglio Regione
    Provincia Comune Ufficio Unione Europea Italia Italiana Giudice Pace
    Sezione Civile Penale Avvocato Avvocata Dott Dottor Sig Signor Signora
    Ing Geom Spett Egregio Gentile Presidente Cancelleria Segreteria Studio
    Associato Gazzetta Ufficiale Decreto Legge Regolamento Ricorso Fattura
    Gennaio Febbraio Marzo Aprile Maggio Giugno Luglio Agosto Settembre
    Ottobre Novembre Dicembre Lunedì Martedì Mercoledì Giovedì Venerdì
    Sabato Domenica
    """.split()
)
SALUTE = re.compile(
    r"\b(prognos[ie]|frattur[ae]|ricover\w*|diagnos[ie]|malatti[ae]"
    r"|terapi[ae]|invalidit[àa]|pronto soccorso|certificat[oi] medic[oi]"
    r"|interventi? chirurgic[oi])\b",
    re.I,
)
SEGNAPOSTO = re.compile(r"\[(?:[A-Z0-9]+_)?([A-Z]+)_(\d+)\]")
MEZZO_NOME = re.compile(
    r"\b([A-ZÀ-Ý][a-zà-ÿ'’]+)[ \t]+"
    r"\[(?:[A-Z0-9]+_)?(?:PERSONA|SOGGETTO)_\d+\]"
)


@functools.cache
def comuni() -> frozenset[str]:
    """I nomi dei comuni italiani (config/comuni.txt, fonte Istat)."""
    righe = COMUNI.read_text("utf-8").splitlines()
    return frozenset(r for r in righe if r and not r.startswith("#"))


# [libro:nomi-rimasti]
def nomi_rimasti(testo: str) -> list[str]:
    """Le parole che sembrano un nome di persona, rimaste fuori dai
    segnaposto: due o tre parole con la maiuscola, che non siano
    istituzioni, inizi di frase o nomi di comuni; o una parola con la
    maiuscola subito prima di un segnaposto, metà di un nome."""
    trovati = set()
    for m in NOME_PROPRIO.finditer(testo):
        parole = m.group(0).split()
        while parole and parole[0] in FERME:
            parole.pop(0)
        while parole and parole[-1] in FERME:
            parole.pop()
        if len(parole) < 2 or any(p in FERME for p in parole):
            continue
        nome = " ".join(parole)
        if nome in comuni() or all(p in comuni() for p in parole):
            continue
        trovati.add(nome)
    # Mezzo nome scoperto: «Alessandro [SOGGETTO_1]».
    for m in MEZZO_NOME.finditer(testo):
        parola = m.group(1)
        if parola not in FERME and parola not in comuni():
            trovati.add(parola)
    return sorted(trovati)


# [/libro:nomi-rimasti]


def salute(testo: str) -> list[str]:
    """Le parole che parlano di salute, un dato particolare (art. 9 GDPR)."""
    return sorted({m.group(0).lower() for m in SALUTE.finditer(testo)})


@dataclass
class Preparato:
    """Il testo che partirebbe, con l'esito dei controlli."""

    testo: str  # pseudonimizzato: è ciò che riceverebbe il fornitore
    tabella: dict[str, str]  # segnaposto -> valore vero: resta nello studio
    fughe: list[str] = field(default_factory=list)
    nomi: list[str] = field(default_factory=list)
    salute: list[str] = field(default_factory=list)

    @property
    def bloccato(self) -> bool:
        return bool(self.fughe or self.nomi)

    def controllo(self, persone: int) -> str:
        """La riga del controllo nel registro dell'uso dell'AI (lezione 8)."""
        return (
            f"elenco di {persone} persone; fughe: {len(self.fughe)}; "
            f"nomi fuori elenco: {len(self.nomi)}"
        )


def _riprendi(pseudonimi: Pseudonimizzatore, tabella: dict[str, str]):
    """I segnaposto già usati nel fascicolo: stesso nome, stesso segno."""
    for segno, valore in tabella.items():
        pseudonimi.tabella[segno] = valore
        pseudonimi._valori[valore] = segno
        trovato = SEGNAPOSTO.fullmatch(segno)
        if trovato:
            tipo, numero = trovato.group(1), int(trovato.group(2))
            attuale = pseudonimi._contatori.get(tipo, 0)
            pseudonimi._contatori[tipo] = max(attuale, numero)


def _unisci(testo: str, tabella: dict[str, str]) -> str:
    """Una persona, un segnaposto: «Bellini» e «BELLINI» prendono quello di
    «Marco Bellini», se non possono essere di nessun altro."""
    interi = {s: v for s, v in tabella.items() if " " in v.strip()}
    for segno, valore in list(tabella.items()):
        if segno in interi:
            continue
        parole = set(valore.casefold().split())
        tipo = SEGNAPOSTO.fullmatch(segno)
        padri = [
            s
            for s, v in interi.items()
            if parole <= set(v.casefold().split())
            and tipo
            and SEGNAPOSTO.fullmatch(s).group(1) == tipo.group(1)
        ]
        if len(padri) == 1:
            testo = testo.replace(segno, padri[0])
            del tabella[segno]
    return testo


# [libro:prepara]
def prepara(
    testo: str, noti: dict[str, str], tabella: dict[str, str] | None = None
) -> Preparato:
    """Pseudonimizza il testo con i nomi noti e i segnaposto già usati,
    poi cerca ciò che resta: fughe, nomi fuori elenco, dati sulla salute."""
    pseudonimi = Pseudonimizzatore(noti=noti, solo_cognomi=True)
    _riprendi(pseudonimi, tabella or {})
    nascosto = pseudonimi.nascondi(testo)
    sensibili = sorted(set(noti) | set(pseudonimi.tabella.values()))
    tabella_nuova = dict(pseudonimi.tabella)
    nascosto = _unisci(nascosto, tabella_nuova)
    return Preparato(
        testo=nascosto,
        tabella=tabella_nuova,
        fughe=fughe(nascosto, sensibili),
        nomi=nomi_rimasti(nascosto),
        salute=salute(nascosto),
    )


# [/libro:prepara]


def ricomponi(testo: str, tabella: dict[str, str]) -> str:
    """Rimette i valori veri al posto dei segnaposto, solo quelli noti."""
    pseudonimi = Pseudonimizzatore()
    _riprendi(pseudonimi, tabella)
    return pseudonimi.ricomponi(testo)


def segnaposto_sconosciuti(testo: str, tabella: dict[str, str]) -> list[str]:
    """I segnaposto della risposta che la tabella non conosce: il modello
    li ha inventati, e nessuno sa a chi si riferiscano."""
    return sorted(
        {m.group(0) for m in SEGNAPOSTO.finditer(testo)} - set(tabella)
    )
