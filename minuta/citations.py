"""Le citazioni non si inventano: estrarle, verificarle, controllarle in ogni bozza.

Il massimario dello studio raccoglie le norme e le sentenze che lo studio
cita davvero. Ogni voce si verifica una volta sulla fonte ufficiale e poi si
riusa. Una citazione che non è nel massimario resta «da verificare»:
la bozza lo dichiara, e l'avvocato decide.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ORDINALI = {"primo": 1, "secondo": 2, "terzo": 3, "quarto": 4, "quinto": 5}

# Gli atti che lo studio cita, con l'identificativo stabile di Normattiva.
ATTI_NORMATIVI = {
    "c.p.c.": ("codice di procedura civile", "urn:nir:stato:regio.decreto:1940-10-28;1443:1"),
    "c.c.": ("codice civile", "urn:nir:stato:regio.decreto:1942-03-16;262:2"),
    "d.lgs. 231/2002": ("D.Lgs. 9 ottobre 2002, n. 231",
                        "urn:nir:stato:decreto.legislativo:2002-10-09;231"),
    "d.p.r. 115/2002": ("D.P.R. 30 maggio 2002, n. 115",
                        "urn:nir:presidente.repubblica:decreto:2002-05-30;115"),
}

CODICE = re.compile(
    r"\bart(?:t)?\.\s*(?P<numeri>\d+(?:-[a-z]+)?(?:\s*(?:,|e)\s*\d+(?:-[a-z]+)?)*)"
    r"(?:\s*(?:e\s+(?:seguenti|ss\.)))?"
    r"(?:,\s*(?P<comma>primo|secondo|terzo|quarto|quinto)\s+comma,)?"
    r"\s*(?P<codice>c\.p\.c\.|c\.c\.)", re.I)
DECRETO = re.compile(
    r"\bart\.\s*(?P<numero>\d+)(?:,\s*(?:primo|secondo|terzo)\s+comma,)?\s+"
    r"(?:del\s+)?(?P<tipo>D\.Lgs\.|D\.P\.R\.)\s*"
    r"(?:\d{1,2}\s+[a-z]+\s+(?P<anno_esteso>\d{4}),\s*n\.\s*(?P<num_esteso>\d+)"
    r"|(?P<num_breve>\d+)/(?P<anno_breve>\d{4}))", re.I)
MEDESIMO = re.compile(r"\bart\.\s*(?P<numero>\d+)\s+del medesimo decreto", re.I)
RINVIO_BREVE = re.compile(r"\(art\.\s*(?P<numero>\d+)\)")
CAUSA_UE = re.compile(r"\bC-(?P<numero>\d+)/(?P<anno>\d{2})\b")
SENTENZA = re.compile(
    r"\bCass\.(?:\s*civ\.)?(?:,\s*(?:sez\.\s*[\w.]+|Sez\.\s*Un\.|S\.U\.))?,?\s*"
    r"(?P<giorno>\d{1,2})\s+(?P<mese>[a-z]+)\s+(?P<anno>\d{4}),?\s*n\.\s*(?P<numero>\d+)",
    re.I)


@dataclass(frozen=True)
class Citazione:
    chiave: str      # forma normalizzata, per esempio "c.p.c. art. 642"
    testo: str       # come compare nell'atto
    tipo: str        # "norma" o "sentenza"


def estrai(testo: str) -> list[Citazione]:
    """Tutte le citazioni del testo, in ordine e senza doppioni."""
    trovate: list[tuple[int, Citazione]] = []
    for m in CODICE.finditer(testo):
        codice = m.group("codice").lower()
        for numero in re.split(r"\s*(?:,|e)\s*", m.group("numeri")):
            trovate.append((m.start(), Citazione(f"{codice} art. {numero}", m.group(0), "norma")))
    ultimo_decreto = None
    eventi: list[tuple[int, str, re.Match]] = []
    for regola, nome in ((DECRETO, "decreto"), (MEDESIMO, "medesimo"), (RINVIO_BREVE, "breve")):
        eventi += [(m.start(), nome, m) for m in regola.finditer(testo)]
    for posizione, nome, m in sorted(eventi, key=lambda e: e[0]):
        if nome == "decreto":
            anno = m.group("anno_esteso") or m.group("anno_breve")
            numero_atto = m.group("num_esteso") or m.group("num_breve")
            ultimo_decreto = f"{m.group('tipo').lower()} {numero_atto}/{anno}"
            chiave = f"{ultimo_decreto} art. {m.group('numero')}"
        elif ultimo_decreto:
            chiave = f"{ultimo_decreto} art. {m.group('numero')}"
        else:
            continue
        trovate.append((posizione, Citazione(chiave, m.group(0), "norma")))
    for m in SENTENZA.finditer(testo):
        chiave = f"cass. {m.group('numero')}/{m.group('anno')}"
        trovate.append((m.start(), Citazione(chiave, m.group(0), "sentenza")))
    for m in CAUSA_UE.finditer(testo):
        chiave = f"cgue C-{m.group('numero')}/{m.group('anno')}"
        trovate.append((m.start(), Citazione(chiave, m.group(0), "sentenza")))
    viste, risultato = set(), []
    for _, citazione in sorted(trovate, key=lambda t: t[0]):
        if citazione.chiave not in viste:
            viste.add(citazione.chiave)
            risultato.append(citazione)
    return risultato


def indirizzo_normattiva(chiave: str) -> str | None:
    """L'indirizzo dell'articolo su Normattiva, se l'atto è fra quelli noti."""
    m = re.match(r"(.+) art\. (\d+)", chiave)
    if not m or m.group(1) not in ATTI_NORMATIVI:
        return None
    urn = ATTI_NORMATIVI[m.group(1)][1]
    return f"https://www.normattiva.it/uri-res/N2Ls?{urn}~art{m.group(2)}"


def verifica_su_normattiva(chiave: str, *, timeout: int = 30) -> dict:
    """Apre l'articolo sul sito ufficiale e controlla che esista.

    Verifica che l'articolo esista, non che dica ciò che l'atto gli fa dire:
    quello resta compito dell'avvocato.
    """
    indirizzo = indirizzo_normattiva(chiave)
    esito = {"chiave": chiave, "indirizzo": indirizzo, "verificata_il": date.today().isoformat()}
    if not indirizzo:
        return {**esito, "stato": "da verificare", "motivo": "atto non collegato a Normattiva"}
    richiesta = urllib.request.Request(indirizzo, headers={"User-Agent": "Mozilla/5.0 (Minuta)"})
    try:
        with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
            pagina = risposta.read().decode("utf-8", "replace")
    except OSError as errore:
        return {**esito, "stato": "da verificare", "motivo": f"sito non raggiungibile: {errore}"}
    numero = chiave.rsplit(" ", 1)[1]
    testo = re.sub(r"<[^>]+>", " ", pagina)
    titolo = re.search(rf"\bArt\.\s*{numero}\b", testo)
    abrogato = re.search(rf"Art\.\s*{numero}\b[^A-Za-z]{{0,20}}\(\(\s*(?:ARTICOLO|PROVVEDIMENTO) ABROGAT", testo)
    if not titolo:
        return {**esito, "stato": "da verificare", "motivo": "articolo non trovato nella pagina"}
    if abrogato:
        return {**esito, "stato": "da verificare", "motivo": "risulta abrogato nel testo vigente"}
    return {**esito, "stato": "verificata", "fonte": "Normattiva, testo vigente"}


class Massimario:
    """Le citazioni dello studio, verificate una volta e poi riusate."""

    def __init__(self, percorso: Path):
        self.percorso = percorso
        self.voci: dict[str, dict] = (
            json.loads(percorso.read_text("utf-8")) if percorso.exists() else {})

    def salva(self) -> None:
        self.percorso.write_text(json.dumps(self.voci, ensure_ascii=False, indent=2) + "\n",
                                 "utf-8")

    def ammesse(self) -> list[str]:
        return sorted(k for k, v in self.voci.items() if v.get("stato") == "verificata")

    def stato(self, citazione: Citazione) -> str:
        voce = self.voci.get(citazione.chiave)
        if voce and voce.get("stato") == "verificata":
            return "verificata"
        if voce:
            return "da verificare: nel massimario, non ancora controllata sulla fonte"
        if citazione.tipo == "sentenza":
            return "da verificare: sentenza non presente nel massimario"
        return "da verificare: norma non presente nel massimario"


def controlla(testo: str, massimario: Massimario) -> list[dict]:
    """Lo stato di ogni citazione di una bozza."""
    return [{"citazione": c.testo, "chiave": c.chiave, "stato": massimario.stato(c)}
            for c in estrai(testo)]
