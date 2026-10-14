"""Minuta per un altro studio (lezione 39): che cosa non si consegna.

Uno studio che dà Minuta a un altro studio consegna il codice, non la
propria installazione. Il repository del laboratorio non contiene dati: il
file .gitignore tiene fuori il database, la cartella dei dati, le copie di
sicurezza e il file .env con la chiave del fornitore. Un'installazione
invece li contiene, e una copia di sicurezza li contiene tutti.

Restano i testi che parlano dello studio: l'informativa ai clienti, la
valutazione d'impatto, le regole di conservazione, l'intestazione degli
atti. Sono giusti per lo studio che li ha scritti e sbagliati per
chiunque altro, e vanno riscritti dal nuovo studio, non ritoccati.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .copie import copie_della_cartella
from .db import AttoArchivio, Documento, Fascicolo, UsoAI, Utente

RADICE = Path(__file__).resolve().parents[1]
CARTELLE = ("config", "docs", "app/templates")


@dataclass
class Esame:
    dati: dict[str, int]
    copie: int
    env: bool
    file: list[tuple[str, list[str]]]

    @property
    def si_consegna(self) -> bool:
        return not any(self.dati.values()) and not self.copie and not self.env


def nomi_dello_studio(db: Session, radice: Path = RADICE) -> list[str]:
    """Il nome dello studio, il suo indirizzo e le persone: dalla
    configurazione dell'intestazione e dagli utenti di Minuta."""
    studio = json.loads((radice / "config" / "studio.json").read_text("utf-8"))
    nomi = {studio["studio"], studio["indirizzo"]}
    nomi |= {a["nome"] for a in studio["avvocati"]}
    nomi |= set(db.scalars(select(Utente.nome)))
    return sorted(nomi)


def file_dello_studio(
    nomi: list[str], radice: Path = RADICE
) -> list[tuple[str, list[str]]]:
    """I file del codice che nominano lo studio o le sue persone."""
    trovati = []
    for cartella in CARTELLE:
        # In ordine di testo: su Windows i percorsi si confrontano senza
        # distinguere le maiuscole, e l'elenco cambierebbe da un sistema
        # all'altro.
        for percorso in sorted(
            (radice / cartella).rglob("*"), key=lambda p: p.as_posix()
        ):
            if not percorso.is_file():
                continue
            testo = percorso.read_text("utf-8", errors="ignore")
            dentro = [
                n for n in nomi if re.search(rf"\b{re.escape(n)}\b", testo)
            ]
            if dentro:
                trovati.append(
                    (percorso.relative_to(radice).as_posix(), dentro)
                )
    return trovati


# [libro:consegna]
def esamina(db: Session, settings: Settings, radice: Path = RADICE) -> Esame:
    """Che cosa, di questa installazione, è dello studio: i dati, le copie,
    la chiave, i testi che lo nominano."""
    dati = {
        "persone dello studio": db.scalar(
            select(func.count()).select_from(Utente)
        ),
        "fascicoli": db.scalar(select(func.count()).select_from(Fascicolo)),
        "documenti": db.scalar(select(func.count()).select_from(Documento)),
        "atti dell'archivio": db.scalar(
            select(func.count()).select_from(AttoArchivio)
        ),
        "voci del registro dell'uso dell'AI": db.scalar(
            select(func.count()).select_from(UsoAI)
        ),
    }
    copie = len(copie_della_cartella(Path(settings.copie_dir)))
    env = radice / ".env"
    chiave = env.is_file() and bool(
        re.search(
            r"^\s*\w*API_KEY\s*=\s*\S", env.read_text("utf-8"), re.MULTILINE
        )
    )
    nomi = nomi_dello_studio(db, radice)
    return Esame(dati, copie, chiave, file_dello_studio(nomi, radice))


# [/libro:consegna]
