"""L'insieme di addestramento di un avvocato (lezione 28): i suoi atti
dell'archivio, senza nomi e senza fatti, in un file che resta nello studio.

Nessun modello viene addestrato qui, e niente parte: l'addestramento vero
si fa su un modello che gira nello studio (lezione 30). Gli atti approvati
da bozze di Minuta non ci sono, perché non sono nell'archivio: un modello
che impara da ciò che ha scritto lui stesso scivola verso il suo stile.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.addestramento import fatti_rimasti, senza_fatti
from minuta.archivio import etichetta
from minuta.invio import nomi_rimasti
from minuta.stile import generico

from .archivio import persone_di
from .config import Settings
from .db import AttoArchivio, Utente
from .web import registra_evento

SEGNAPOSTO = ("[IMPORTO]", "[DATA]", "[ANNO]", "[NUMERO]")


class AddestramentoRifiutato(Exception):
    """L'insieme non si prepara: il messaggio dice perché."""


@dataclass
class Insieme:
    percorso: Path
    atti: int
    parole: int
    tolti: dict[str, int]  # quanti segnaposto di ogni tipo
    impronta: str


# [libro:prepara-insieme]
def prepara_insieme(
    db: Session, settings: Settings, utente: Utente
) -> Insieme:
    """Gli atti dell'avvocato, con i nomi in segnaposto senza numero, come
    per il profilo, e senza importi, date, anni e numeri dei documenti. Se
    resta un nome o un fatto, il file non si scrive."""
    if utente.ruolo != "avvocato":
        raise AddestramentoRifiutato("L'insieme è degli atti di un avvocato.")
    atti = list(
        db.scalars(
            select(AttoArchivio)
            .where(AttoArchivio.autore_id == utente.id)
            .order_by(AttoArchivio.id)
        )
    )
    if len(atti) < 2:
        raise AddestramentoRifiutato("Servono almeno due atti nell'archivio.")
    studio = {
        u.nome: "PERSONA"
        for u in db.scalars(select(Utente))
        if len(u.nome.split()) >= 2
    }
    righe, tolti = [], dict.fromkeys(SEGNAPOSTO, 0)
    for atto in atti:  # l'etichetta è quella dell'archivio (lezione 22)
        senza_nomi = generico(
            "\n".join(json.loads(atto.pagine)), studio | persone_di(atto)
        )
        testo = senza_fatti(senza_nomi)
        rimasti = nomi_rimasti(testo) + fatti_rimasti(testo)
        if rimasti:
            raise AddestramentoRifiutato(
                f"Nell'atto {etichetta(atto.id)} resta: {'; '.join(rimasti)}."
            )
        for s in SEGNAPOSTO:
            tolti[s] += testo.count(s) - senza_nomi.count(s)
        righe.append(
            {"atto": etichetta(atto.id), "tipo": atto.tipo, "testo": testo}
        )
    contenuto = "".join(
        json.dumps(r, ensure_ascii=False) + "\n" for r in righe
    )
    percorso = (
        Path(settings.data_dir)
        / "addestramento"
        / f"{utente.nome_utente}.jsonl"
    )
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(contenuto, "utf-8")
    impronta = hashlib.sha256(contenuto.encode()).hexdigest()
    registra_evento(
        db, utente, None, "addestramento", atti=len(atti), impronta=impronta
    )
    db.commit()
    parole = sum(len(r["testo"].split()) for r in righe)
    return Insieme(percorso, len(atti), parole, tolti, impronta)


# [/libro:prepara-insieme]
