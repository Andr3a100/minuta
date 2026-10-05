"""L'archivio dello studio: legge gli atti, li divide in sezioni, li indicizza.

L'archivio resta nello studio: il testo originale sta solo nel database
locale. Al fornitore del modello non arriva mai da qui.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}

# Le sezioni di un atto, con le parole che le annunciano nei due stili dello
# studio: «PREMESSO CHE» e le sezioni numerate («1. I fatti»).
RUOLI = [
    ("procura", re.compile(r"^procura alle liti", re.I)),
    ("fatti", re.compile(r"^(premesso che|\d+\.\s+i fatti)", re.I)),
    ("diritto", re.compile(
        r"^(considerato che|\d+\.\s+(il credito|gli interessi|la prova))", re.I)),
    ("conclusioni", re.compile(r"^(tutto ciò premesso|chiede$|\d+\.\s+conclusioni)", re.I)),
    ("documenti", re.compile(r"^(si producono|documenti)\s*:", re.I)),
]

DATA_LUOGO = re.compile(
    r"^[A-Z][a-zà-ù]+(?: [a-zà-ù]+)*, (\d{1,2})°? ([a-z]+) (\d{4})$")
IMPORTO = r"(\d{1,3}(?:\.\d{3})*,\d{2})"


@dataclass
class Atto:
    id: str
    file: str
    testo: str
    paragrafi: list[str]
    sezioni: list[tuple[str, str]] = field(default_factory=list)  # (ruolo, testo)
    data: str | None = None
    autore: str | None = None
    tipo: str | None = None
    giudice: str | None = None
    valore: float | None = None


def normalizza(testo: str) -> str:
    """Toglie legature e sillabazioni, unisce le righe di un paragrafo."""
    testo = unicodedata.normalize("NFKC", testo)
    testo = re.sub(r"-\n(?=[a-zà-ù])", "", testo)
    return re.sub(r"\s*\n\s*", " ", testo).strip()


def leggi_pdf(percorso: Path) -> list[str]:
    """I paragrafi del PDF, uno per blocco di testo, nell'ordine di lettura."""
    paragrafi = []
    with pymupdf.open(percorso) as documento:
        for pagina in documento:
            for blocco in pagina.get_text("blocks", sort=True):
                testo = normalizza(blocco[4])
                if testo:
                    paragrafi.append(testo)
    return paragrafi


def importo(testo: str) -> float:
    return float(testo.replace(".", "").replace(",", "."))


def ruolo_del_titolo(paragrafo: str) -> str | None:
    breve = len(paragrafo) <= 80
    for ruolo, regola in RUOLI:
        if regola.search(paragrafo) and (breve or ruolo in ("documenti", "conclusioni")):
            return ruolo
    return None


def dividi(paragrafi: list[str]) -> list[tuple[str, str]]:
    """Divide l'atto in sezioni: intestazione, fatti, diritto, conclusioni..."""
    sezioni: list[tuple[str, list[str]]] = [("intestazione", [])]
    for paragrafo in paragrafi:
        ruolo = ruolo_del_titolo(paragrafo)
        if ruolo and ruolo != sezioni[-1][0]:
            sezioni.append((ruolo, [paragrafo]))
        elif DATA_LUOGO.match(paragrafo) and sezioni[-1][0] != "intestazione":
            sezioni.append(("firma", [paragrafo]))
        else:
            sezioni[-1][1].append(paragrafo)
    return [(ruolo, "\n".join(testi)) for ruolo, testi in sezioni if testi]


def metadati(atto: Atto, avvocati: list[dict]) -> None:
    testo = "\n".join(atto.paragrafi)
    giudice = re.search(r"(TRIBUNALE(?: ORDINARIO)?|GIUDICE DI PACE) DI ([A-ZÀ-Ù' ]+)",
                        testo, re.I)
    if giudice:
        tipo = "Tribunale" if giudice.group(1).upper().startswith("TRIBUNALE") else "Giudice di Pace"
        atto.giudice = f"{tipo} di {giudice.group(2).strip().title()}"
    if re.search(r"oggetto:\s*diffida", testo, re.I):
        atto.tipo = "diffida e messa in mora"
        atto.giudice = None
    elif re.search(r"ricorso per (decreto ingiuntivo|ingiunzione di pagamento)", testo, re.I):
        atto.tipo = "ricorso decreto ingiuntivo"
        if re.search(r"provvisoriamente esecutivo", testo, re.I):
            atto.tipo += " provvisoriamente esecutivo"
    date = [m for p in atto.paragrafi if (m := DATA_LUOGO.match(p))]
    if date:
        # La data dell'atto è quella prima della firma; la procura ne ha un'altra,
        # precedente. Nella lettera la data è in alto: è comunque la prima.
        giorno, mese, anno = date[0].groups()
        atto.data = f"{anno}-{MESI[mese]:02d}-{int(giorno):02d}"
    for avvocato in avvocati:
        if re.search(rf"Avv\. {re.escape(avvocato['nome'])}\s*$", testo, re.M):
            atto.autore = avvocato["id"]
    valore = (re.search(rf"valore della (?:presente procedura|causa)[^\n]*?euro {IMPORTO}", testo, re.I)
              or re.search(rf"(?:somma|pagamento|totale) di euro {IMPORTO}", testo, re.I))
    if valore:
        atto.valore = importo(valore.group(1))


def leggi_atto(percorso: Path, avvocati: list[dict]) -> Atto:
    paragrafi = leggi_pdf(percorso)
    atto = Atto(id=percorso.stem[:2], file=percorso.stem, testo="\n".join(paragrafi),
                paragrafi=paragrafi)
    atto.sezioni = dividi(paragrafi)
    metadati(atto, avvocati)
    return atto


SCHEMA = """
create table if not exists atti(
    id text primary key, file text, data text, autore text, tipo text,
    giudice text, valore real, testo text);
create table if not exists sezioni(
    atto_id text, ordine integer, ruolo text, testo text);
create virtual table if not exists indice using fts5(
    atto_id unindexed, ruolo unindexed, testo, tokenize='trigram');
create table if not exists riservati(
    atto_id text, valore text, tipo text);
"""


def apri(percorso_db: Path) -> sqlite3.Connection:
    db = sqlite3.connect(percorso_db)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def importa(cartella: Path, db: sqlite3.Connection, config: dict) -> list[Atto]:
    """Legge tutti i PDF della cartella e li mette nell'archivio locale."""
    atti = [leggi_atto(p, config["avvocati"]) for p in sorted(cartella.glob("*.pdf"))]
    with db:
        for atto in atti:
            db.execute("delete from atti where id = ?", (atto.id,))
            db.execute("delete from sezioni where atto_id = ?", (atto.id,))
            db.execute("delete from indice where atto_id = ?", (atto.id,))
            db.execute("delete from riservati where atto_id = ?", (atto.id,))
            db.execute("insert into atti values (?, ?, ?, ?, ?, ?, ?, ?)",
                       (atto.id, atto.file, atto.data, atto.autore, atto.tipo,
                        atto.giudice, atto.valore, atto.testo))
            for ordine, (ruolo, testo) in enumerate(atto.sezioni):
                db.execute("insert into sezioni values (?, ?, ?, ?)",
                           (atto.id, ordine, ruolo, testo))
                db.execute("insert into indice values (?, ?, ?)", (atto.id, ruolo, testo))
    return atti


def importa_testo(db: sqlite3.Connection, atto_id: str, file: str, testo: str, *, autore: str,
                  tipo: str, giudice: str | None, valore: float | None, data: str,
                  riservati: dict[str, str] | None = None) -> Atto:
    """Un atto firmato, arrivato come testo: entra fra gli esempi dello studio.

    riservati sono i dati del suo cliente, presi dal fascicolo: quando l'atto
    farà da esempio per un altro cliente, si nascondono anche se nessuna regola
    li riconoscerebbe (un nome senza titolo, una forma abbreviata).
    """
    paragrafi = [normalizza(p) for p in re.split(r"\n\s*\n", testo) if p.strip()]
    righe = [r for p in paragrafi for r in ([p] if len(p) > 80 else p.split("\n")) if r]
    atto = Atto(id=atto_id, file=file, testo="\n".join(righe), paragrafi=righe, data=data,
                autore=autore, tipo=tipo, giudice=giudice, valore=valore)
    atto.sezioni = dividi(righe)
    with db:
        for tabella in ("atti", "sezioni", "indice", "riservati"):
            colonna = "id" if tabella == "atti" else "atto_id"
            db.execute(f"delete from {tabella} where {colonna} = ?", (atto_id,))
        db.execute("insert into atti values (?, ?, ?, ?, ?, ?, ?, ?)",
                   (atto.id, atto.file, atto.data, atto.autore, atto.tipo, atto.giudice,
                    atto.valore, atto.testo))
        for ordine, (ruolo, testo_sezione) in enumerate(atto.sezioni):
            db.execute("insert into sezioni values (?, ?, ?, ?)", (atto.id, ordine, ruolo, testo_sezione))
            db.execute("insert into indice values (?, ?, ?)", (atto.id, ruolo, testo_sezione))
        for valore_riservato, tipo_riservato in (riservati or {}).items():
            db.execute("insert into riservati values (?, ?, ?)",
                       (atto.id, valore_riservato, tipo_riservato))
    return atto


def riservati(db: sqlite3.Connection, atto_id: str) -> dict[str, str]:
    return {r["valore"]: r["tipo"] for r in
            db.execute("select valore, tipo from riservati where atto_id = ?", (atto_id,))}


def approvati(db: sqlite3.Connection) -> set[str]:
    """Gli atti entrati nell'archivio da una bozza di Minuta approvata."""
    return {r["id"] for r in db.execute("select id from atti where file like 'approvati/%'")}


def salva_approvato(cartella: Path, testo: str, scheda: dict) -> Path:
    """L'atto firmato resta in due file, testo e scheda: il database si può sempre
    ricostruire, gli atti firmati non vanno persi."""
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / f"{scheda['atto_id']}.txt").write_text(testo + "\n", "utf-8")
    percorso = cartella / f"{scheda['atto_id']}.json"
    percorso.write_text(json.dumps(scheda, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return percorso


def importa_approvato(percorso: Path, db: sqlite3.Connection) -> Atto:
    scheda = json.loads(percorso.read_text("utf-8"))
    testo = (percorso.parent / f"{scheda['atto_id']}.txt").read_text("utf-8")
    return importa_testo(db, file=f"approvati/{scheda['atto_id']}", testo=testo, **scheda)


def importa_approvati(cartella: Path, db: sqlite3.Connection) -> list[Atto]:
    return [importa_approvato(p, db) for p in sorted(cartella.glob("*.json"))]


def carica_config(percorso: Path) -> dict:
    return json.loads(percorso.read_text("utf-8"))
