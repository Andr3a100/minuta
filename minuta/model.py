"""Il livello fra Minuta e il fornitore del modello.

Minuta parla con qualunque modello attraverso la stessa interfaccia: si
cambia fornitore cambiando configurazione, non codice. Le chiavi si leggono
dalle variabili d'ambiente e non si stampano mai.

ModelloFinto non è un modello: è un sostituto deterministico per le prove
automatiche, gratuito e ripetibile. Compone la bozza con regole fisse, dal
fascicolo e dagli esempi che riceve. La qualità della scrittura si misura
solo con un modello vero, e quelle esecuzioni diventano verbali datati.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Risposta:
    testo: str
    modello: str
    token_in: int | None = None
    token_out: int | None = None


class Modello(Protocol):
    nome: str

    def scrivi(self, sistema: str, richiesta: str) -> Risposta: ...


class ModelloAnthropic:
    """Messages API di Anthropic. Chiave in ANTHROPIC_API_KEY."""

    def __init__(self, nome: str = "claude-sonnet-5-5", massimo: int = 4000):
        self.nome = nome
        self.massimo = massimo

    def scrivi(self, sistema: str, richiesta: str) -> Risposta:
        corpo = json.dumps({
            "model": self.nome, "max_tokens": self.massimo, "system": sistema,
            "messages": [{"role": "user", "content": richiesta}],
        }).encode()
        domanda = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=corpo, method="POST",
            headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                     "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(domanda, timeout=300) as r:
            dati = json.load(r)
        testo = "".join(b.get("text", "") for b in dati["content"] if b.get("type") == "text")
        uso = dati.get("usage", {})
        return Risposta(testo, dati.get("model", self.nome), uso.get("input_tokens"),
                        uso.get("output_tokens"))


def chiave_openai() -> str:
    return os.environ.get("OPENAI_API_KEY") or os.environ["MINUTA_API_KEY"]


def carica_env(percorso: Path) -> None:
    """Legge le chiavi da un file .env locale, senza mai stamparle."""
    if not percorso.exists():
        return
    for riga in percorso.read_text("utf-8").splitlines():
        riga = riga.strip()
        if riga and not riga.startswith("#") and "=" in riga:
            nome, valore = riga.split("=", 1)
            if valore.strip():
                os.environ.setdefault(nome.strip(), valore.strip())


def modelli_openai(indirizzo: str = "https://api.openai.com/v1") -> list[str]:
    """I modelli disponibili sull'account: solo i nomi."""
    domanda = urllib.request.Request(f"{indirizzo}/models",
                                     headers={"authorization": f"Bearer {chiave_openai()}"})
    with urllib.request.urlopen(domanda, timeout=60) as r:
        return sorted(m["id"] for m in json.load(r)["data"])


class ModelloCompatibileOpenAI:
    """OpenAI, o qualunque servizio con la stessa interfaccia chat/completions.

    Chiave in OPENAI_API_KEY; indirizzo diverso da OpenAI in MINUTA_BASE_URL.
    """

    def __init__(self, nome: str, indirizzo: str | None = None, massimo: int = 4000):
        self.nome = nome
        self.indirizzo = (indirizzo or os.environ.get("MINUTA_BASE_URL")
                          or "https://api.openai.com/v1").rstrip("/")
        self.massimo = massimo

    def scrivi(self, sistema: str, richiesta: str) -> Risposta:
        corpo = json.dumps({
            "model": self.nome, "max_completion_tokens": self.massimo,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": richiesta}],
        }).encode()
        domanda = urllib.request.Request(
            f"{self.indirizzo}/chat/completions", data=corpo, method="POST",
            headers={"authorization": f"Bearer {chiave_openai()}",
                     "content-type": "application/json"})
        with urllib.request.urlopen(domanda, timeout=300) as r:
            dati = json.load(r)
        uso = dati.get("usage", {})
        return Risposta(dati["choices"][0]["message"]["content"], dati.get("model", self.nome),
                        uso.get("prompt_tokens"), uso.get("completion_tokens"))


class ModelloFinto:
    """Sostituto deterministico per le prove: nessuna rete, nessun costo.

    errore: "sentenza" aggiunge una sentenza inventata; "contaminazione" usa
    un segnaposto di un esempio. Servono agli errori deliberati.
    """

    nome = "finto-deterministico"

    def __init__(self, errore: str | None = None):
        self.errore = errore

    def scrivi(self, sistema: str, richiesta: str) -> Risposta:
        dati = dict(re.findall(r"^([A-Z_ ]+): (.+)$", richiesta.split("ESEMPIO E1", 1)[0], re.M))
        stile = json.loads(re.search(r"^STILE: (\{.*\})$", richiesta, re.M).group(1))
        esempio = re.search(r"ESEMPIO E1 [^\n]*\n(.*?)(?:\nESEMPIO E2|\nFINE ESEMPI)",
                            richiesta, re.S).group(1)
        # Dall'esempio si riprendono solo i paragrafi di diritto senza segnaposto:
        # sono il ragionamento dello studio, non i fatti di un altro cliente.
        ripresi = [p for p in esempio.split("\n")
                   if re.search(r"art(?:t)?\.\s*\d+", p) and "[" not in p and len(p) > 80][:2]
        p = []
        p.append(f"{stile['intestazione']} {{fonte: profilo}}")
        p.append(f"{stile['titolo']} {{fonte: profilo}}")
        p.append(f"Per: {dati['RICORRENTE']} (P.IVA {dati['PIVA RICORRENTE']}), con sede in "
                 f"{dati['SEDE RICORRENTE']}, in persona del legale rappresentante "
                 f"{dati['RAPPRESENTANTE']}, rappresentata e difesa dall'Avv. {dati['AVVOCATO']}. "
                 f"{{fonte: fascicolo}}")
        p.append(f"contro: {dati['INTIMATA']} (P.IVA {dati['PIVA INTIMATA']}), con sede in "
                 f"{dati['SEDE INTIMATA']}. {{fonte: fascicolo}}")
        p.append(f"{stile['fatti']} {{fonte: profilo}}")
        p.append(f"1. la ricorrente ha eseguito per conto dell'intimata {dati['RAPPORTO']}; "
                 f"le fatture {dati['FATTURE']}, per complessivi euro {dati['TOTALE']}, sono "
                 f"scadute e non pagate, nonostante la diffida del {dati['DIFFIDA']}. "
                 f"{{fonte: fascicolo}}")
        p.append(f"{stile['diritto']} {{fonte: profilo}}")
        p += [f"{testo} {{fonte: E1}}" for testo in ripresi]
        if self.errore == "sentenza":
            p.append("come affermato da Cass. civ., sez. II, 15 maggio 2023, n. 99999. "
                     "{fonte: modello}")
        p.append(f"{stile['conclusioni']} {{fonte: profilo}}")
        destinatario = "[E1_SOGGETTO_2]" if self.errore == "contaminazione" else dati["INTIMATA"]
        p.append(f"che l'Ill.mo {dati['GIUDICE']} voglia ingiungere a {destinatario} di pagare "
                 f"alla ricorrente, entro quaranta giorni dalla notifica, la somma di euro "
                 f"{dati['TOTALE']}, oltre interessi moratori ai sensi dell'art. 5 del D.Lgs. "
                 f"231/2002 e spese del procedimento. {{fonte: fascicolo}}")
        p.append(f"Ai sensi dell'art. 14 del D.P.R. 115/2002 si dichiara che il valore della "
                 f"presente procedura è pari a euro {dati['TOTALE']}. {{fonte: profilo}}")
        p.append(f"Si producono: {dati['DOCUMENTI']}. {{fonte: fascicolo}}")
        p.append("[DA COMPLETARE: luogo e data] Avv. " + dati["AVVOCATO"] + " {fonte: fascicolo}")
        testo = "\n\n".join(p)
        return Risposta(testo, self.nome, len(sistema + richiesta) // 4, len(testo) // 4)


def scegli(nome: str | None = None) -> Modello:
    """Il modello indicato in MINUTA_MODELLO: finto, anthropic, openai."""
    nome = nome or os.environ.get("MINUTA_MODELLO", "finto")
    if nome == "finto":
        return ModelloFinto()
    if nome == "anthropic":
        return ModelloAnthropic(os.environ.get("MINUTA_MODELLO_NOME", "claude-sonnet-5-5"))
    if nome == "openai":
        return ModelloCompatibileOpenAI(os.environ["MINUTA_MODELLO_NOME"])
    raise ValueError(f"modello sconosciuto: {nome}")
