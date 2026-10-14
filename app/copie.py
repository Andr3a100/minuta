"""Le copie di sicurezza di Minuta (lezione 33).

Una copia è un solo file, `copie/minuta-AAAA-MM-GG.tar.gz`: il database e
la cartella dei dati, con l'elenco di ciò che contiene e l'impronta di ogni
file. Il database si copia con la funzione di SQLite che lo legge in un
momento solo, anche con Minuta accesa: un file copiato a metà di una
scrittura non si riapre. La chiave del fornitore e il file .env non entrano
nella copia: stanno sul server, non nei dati dello studio.

Una copia vale soltanto se si ripristina. `verifica_copia` la apre in una
cartella temporanea, come un ripristino, confronta le impronte e controlla
il database. `ripristina` la riporta in un Minuta vuoto, il server dello
studio della lezione 30, e rifiuta un database che contiene già dati.

La copia contiene tutto lo studio, in chiaro: nasce leggibile soltanto da
chi la crea, e fuori dal server viaggia cifrata. Le copie più vecchie dei
giorni decisi in config/conservazione.json si tolgono, ogni volta che se
ne fa una nuova: un fascicolo cancellato resta nelle copie fino a quel
giorno, e non oltre.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
import zlib
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.engine import make_url

from . import __version__
from .config import Settings

CONTENUTO = "contenuto.json"
DATABASE = "database.sqlite"
NOME = re.compile(r"minuta-(\d{4}-\d{2}-\d{2})(?:-\d+)?\.tar\.gz")


class CopiaRifiutata(Exception):
    """La copia non si fa, non si verifica o non si ripristina."""


@dataclass
class Copia:
    percorso: Path
    file: int
    fascicoli: list[str]
    tolte: list[str]


@dataclass
class Verifica:
    contenuto: dict
    problemi: list[str]
    fascicoli: int
    persone: int


def percorso_database(settings: Settings) -> Path:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise CopiaRifiutata(
            "Minuta copia un database SQLite; un database PostgreSQL si "
            "copia con pg_dump, lo strumento di PostgreSQL."
        )
    return Path(url.database)


def impronta(percorso: Path) -> str:
    h = hashlib.sha256()
    with percorso.open("rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def file_dei_dati(settings: Settings) -> list[Path]:
    """I file della cartella dei dati, fuori dalla cartella delle copie."""
    dati = Path(settings.data_dir)
    copie = Path(settings.copie_dir).resolve()
    if not dati.is_dir():
        return []
    return sorted(
        p
        for p in dati.rglob("*")
        if p.is_file() and copie not in p.resolve().parents
    )


def leggi_database(percorso: Path) -> tuple[list[str], int, str]:
    """I codici dei fascicoli, le persone dello studio, il controllo di
    integrità di SQLite: «ok» se il database è sano."""
    with closing(sqlite3.connect(percorso)) as conn:
        controllo = conn.execute("PRAGMA integrity_check").fetchone()[0]
        codici = [
            r[0]
            for r in conn.execute("SELECT codice FROM fascicoli ORDER BY 1")
        ]
        persone = conn.execute("SELECT count(*) FROM utenti").fetchone()[0]
    return codici, persone, controllo


def nuovo_nome(cartella: Path, oggi: date) -> Path:
    percorso = cartella / f"minuta-{oggi.isoformat()}.tar.gz"
    n = 2
    while percorso.exists():
        percorso = cartella / f"minuta-{oggi.isoformat()}-{n}.tar.gz"
        n += 1
    return percorso


def fatta_il(percorso: Path) -> date | None:
    trovato = NOME.fullmatch(percorso.name)
    return date.fromisoformat(trovato.group(1)) if trovato else None


def copie_della_cartella(cartella: Path) -> list[Path]:
    if not cartella.is_dir():
        return []
    return sorted(p for p in cartella.iterdir() if fatta_il(p))


# [libro:copia]
def fai_copia(settings: Settings, giorni: int, oggi: date) -> Copia:
    """Il database e i dati in un solo file, con le impronte; poi si
    tolgono le copie più vecchie dei giorni decisi dallo studio."""
    cartella = Path(settings.copie_dir)
    cartella.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / DATABASE
        with closing(sqlite3.connect(percorso_database(settings))) as origine:
            with closing(sqlite3.connect(database)) as copia:
                origine.backup(copia)  # tutto il database, in un momento
        codici, _persone, _controllo = leggi_database(database)
        dati = file_dei_dati(settings)
        base = Path(settings.data_dir)
        nomi = {DATABASE: database}
        for p in dati:
            nomi["dati/" + p.relative_to(base).as_posix()] = p
        contenuto = {
            "minuta": __version__,
            "fatta_il": oggi.isoformat(),
            "fascicoli": codici,
            "impronte": {n: impronta(p) for n, p in nomi.items()},
        }
        (Path(tmp) / CONTENUTO).write_text(
            json.dumps(contenuto, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        percorso = nuovo_nome(cartella, oggi)
        # Leggibile soltanto da chi la crea: dentro c'è tutto lo studio.
        fd = os.open(percorso, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with (
            os.fdopen(fd, "wb") as f,
            tarfile.open(fileobj=f, mode="w:gz") as tar,
        ):
            tar.add(Path(tmp) / CONTENUTO, arcname=CONTENUTO)
            for nome, p in nomi.items():
                tar.add(p, arcname=nome)
    limite = oggi - timedelta(days=giorni)
    tolte = []
    for vecchia in copie_della_cartella(cartella):
        if fatta_il(vecchia) < limite:
            vecchia.unlink()
            tolte.append(vecchia.name)
    return Copia(percorso, len(dati), codici, tolte)


# [/libro:copia]


def apri_copia(percorso: Path, cartella: Path) -> dict:
    """Estrae la copia nella cartella e ne restituisce il contenuto.
    Il filtro «data» rifiuta i nomi che uscirebbero dalla cartella."""
    try:
        with tarfile.open(percorso, "r:gz") as tar:
            tar.extractall(cartella, filter="data")
        testo = (cartella / CONTENUTO).read_text(encoding="utf-8")
    except (OSError, EOFError, zlib.error, tarfile.TarError) as exc:
        # Una copia troncata, per un disco pieno o un trasferimento
        # interrotto, finisce prima del tempo: è gzip a dirlo, non tar.
        raise CopiaRifiutata(f"La copia non si apre: {exc}") from None
    return json.loads(testo)


# [libro:verifica-copia]
def verifica_copia(percorso: Path) -> Verifica:
    """Apre la copia come un ripristino, in una cartella temporanea: ogni
    file con la sua impronta, nessun file in più, il database sano e con
    i fascicoli dell'elenco."""
    with tempfile.TemporaryDirectory() as tmp:
        cartella = Path(tmp)
        contenuto = apri_copia(percorso, cartella)
        attese = contenuto["impronte"]
        problemi = []
        for nome, attesa in attese.items():
            file = cartella / nome
            if not file.is_file():
                problemi.append(f"manca {nome}")
            elif impronta(file) != attesa:
                problemi.append(f"impronta diversa: {nome}")
        for file in sorted(cartella.rglob("*")):
            nome = file.relative_to(cartella).as_posix()
            if file.is_file() and nome != CONTENUTO and nome not in attese:
                problemi.append(f"file in più: {nome}")
        codici, persone = [], 0
        if (cartella / DATABASE).is_file():
            try:
                codici, persone, controllo = leggi_database(
                    cartella / DATABASE
                )
            except sqlite3.DatabaseError as exc:
                controllo = str(exc)
            if controllo != "ok":
                problemi.append(f"database: {controllo}")
            if codici != contenuto["fascicoli"]:
                problemi.append("i fascicoli non sono quelli dell'elenco")
    return Verifica(contenuto, problemi, len(codici), persone)


# [/libro:verifica-copia]


def database_vuoto(percorso: Path) -> bool:
    if not percorso.is_file():
        return True
    with closing(sqlite3.connect(percorso)) as conn:
        tabelle = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        righe = sum(
            conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("utenti", "fascicoli")
            if t in tabelle
        )
    return righe == 0


def ripristina(settings: Settings, percorso: Path) -> Verifica:
    """Riporta una copia verificata in un Minuta che non contiene dati:
    prima tutti i controlli, poi le scritture. Un file dei dati che c'è
    già, uguale, resta com'è; diverso, ferma il ripristino."""
    verifica = verifica_copia(percorso)
    if verifica.problemi:
        raise CopiaRifiutata(
            "La copia non è integra: " + "; ".join(verifica.problemi) + "."
        )
    destinazione = percorso_database(settings)
    if not database_vuoto(destinazione):
        raise CopiaRifiutata(
            "Il database di destinazione contiene già dati: rifiutato."
        )
    base = Path(settings.data_dir)
    with tempfile.TemporaryDirectory() as tmp:
        cartella = Path(tmp)
        contenuto = apri_copia(percorso, cartella)
        da_copiare = []
        for nome, attesa in contenuto["impronte"].items():
            if nome == DATABASE:
                continue
            arrivo = base / nome.removeprefix("dati/")
            if arrivo.is_file():
                if impronta(arrivo) != attesa:
                    raise CopiaRifiutata(
                        f"{arrivo.as_posix()} c'è già, diverso: rifiutato."
                    )
                continue
            da_copiare.append((cartella / nome, arrivo))
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(cartella / DATABASE)) as origine:
            with closing(sqlite3.connect(destinazione)) as arrivo:
                origine.backup(arrivo)
        for sorgente, arrivo in da_copiare:
            arrivo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sorgente, arrivo)
    return verifica


def fascicoli_nelle_copie(
    cartella: Path, giorni: int
) -> dict[str, list[date]]:
    """Per ogni fascicolo nelle copie, il giorno in cui si toglie ciascuna
    copia che lo contiene."""
    trovati: dict[str, list[date]] = {}
    for copia in copie_della_cartella(cartella):
        try:
            with tarfile.open(copia, "r:gz") as tar:
                f = tar.extractfile(CONTENUTO)
                contenuto = json.loads(f.read().decode("utf-8"))
        except (OSError, EOFError, zlib.error, tarfile.TarError, KeyError):
            continue
        si_toglie = fatta_il(copia) + timedelta(days=giorni + 1)
        for codice in contenuto["fascicoli"]:
            trovati.setdefault(codice, []).append(si_toglie)
    return trovati
