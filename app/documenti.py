"""I documenti del fascicolo, nell'applicazione (lezione 16).

Il caricamento segue l'ordine di ogni scrittura: chi sei e su quale
fascicolo (lo controlla chi chiama), se il documento è nuovo; poi la
lettura, con il motore (minuta/documenti.py), e alla fine la scrittura, con
la sua riga nel registro delle attività, nella stessa transazione.
L'originale si salva per primo, con la sua impronta come nome: se la
transazione non riesce resta un file che nessuno usa, mai una riga senza
il suo file.
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta import certificatori
from minuta import documenti as motore

from .config import Settings
from .db import Documento, Fascicolo, Utente
from .web import registra_evento

MASSIMO_DOCUMENTO = 20_000_000  # byte: 20 MB


class DocumentoRifiutato(Exception):
    """Il documento non entra nel fascicolo: il messaggio dice perché."""


def cartella_dati(settings: Settings) -> Path:
    """Dove stanno gli originali e l'elenco dei certificatori."""
    return Path(settings.data_dir)


def originale(settings: Settings, documento: Documento) -> Path:
    return cartella_dati(settings) / "documenti" / documento.impronta


def nome_pulito(nome: str) -> str:
    """Solo il nome del file, senza cartelle e senza caratteri di controllo."""
    nome = re.split(r"[\\/]", nome)[-1]
    nome = "".join(c for c in nome if c.isprintable()).strip()
    return nome[:200] or "documento"


# [libro:carica]
def carica(
    db: Session,
    settings: Settings,
    utente: Utente,
    fascicolo: Fascicolo,
    nome: str,
    dati: bytes,
) -> tuple[Documento, motore.Lettura]:
    """Legge il documento e lo aggiunge al fascicolo, con la sua riga nel
    registro delle attività. Chi chiama ha già controllato chi carica."""
    nome = nome_pulito(nome)
    if not dati:
        raise DocumentoRifiutato("Il file è vuoto.")
    if len(dati) > MASSIMO_DOCUMENTO:
        raise DocumentoRifiutato("Il file supera i 20 MB.")
    impronta = hashlib.sha256(dati).hexdigest()
    gia = db.scalar(
        select(Documento).where(
            Documento.fascicolo_id == fascicolo.id,
            Documento.impronta == impronta,
        )
    )
    if gia is not None:
        raise DocumentoRifiutato(f"È già nel fascicolo, come {gia.nome}.")
    lettura = motore.leggi(nome, dati, cartella_dati(settings))
    cartella = cartella_dati(settings) / "documenti"
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / impronta).write_bytes(dati)  # l'originale, com'è arrivato
    busta = lettura.busta
    documento = Documento(
        fascicolo_id=fascicolo.id,
        nome=nome,
        impronta=impronta,
        byte=len(dati),
        tipo=lettura.tipo,
        pagine=len(lettura.pagine),
        ottica=lettura.ottica,
        nascosti=len(lettura.nascosti),
        integro=busta.integro if busta else None,
        certificato=busta.certificato if busta else None,
        lettura=json.dumps(asdict(lettura), ensure_ascii=False),
        caricato_da_id=utente.id,
    )
    db.add(documento)
    db.flush()
    registra_evento(
        db, utente, fascicolo, "documento", nome=nome, impronta=impronta
    )
    db.commit()  # il documento e la sua riga, insieme o per niente
    return documento, lettura


# [/libro:carica]


def lettura_di(documento: Documento) -> dict:
    return json.loads(documento.lettura)


# [libro:descrivi]
def descrivi(lettura: motore.Lettura | dict) -> list[str]:
    """Le righe con cui Minuta racconta un documento letto."""
    dati = asdict(lettura) if isinstance(lettura, motore.Lettura) else lettura
    pagine = len(dati["pagine"])
    righe = [f"{dati['nome']}: {dati['tipo']}"]
    if pagine:
        righe[0] += f", {pagine} {'pagina' if pagine == 1 else 'pagine'}"
    if any(p["ottica"] for p in dati["pagine"]):
        righe[0] += ", lettura ottica"
    busta = dati["busta"]
    if busta:
        integro = "il documento è quello che è stato firmato"
        righe.append("  integrità: " + (integro if busta["integro"] else "NO"))
        stato = "verificato" if busta["certificato"] else "NON verificato"
        righe.append(f"  certificato: {stato}, {busta['motivo']}")
        if busta["firmatario"]:
            righe.append(f"  firmatario: {busta['firmatario']}")
        righe.append("  revoca e sospensione: non controllate")
    for avviso in dati["avvisi"]:
        righe += textwrap.wrap(
            avviso, 79, initial_indent="  ! ", subsequent_indent="    "
        )
    return righe


# [/libro:descrivi]


def stato_elenco(settings: Settings) -> str:
    """Una riga sull'elenco dei certificatori, per la diagnosi."""
    elenco = certificatori.notizie(cartella_dati(settings))
    if elenco is None:
        return "non scaricato"
    return (
        f"AgID n. {elenco.numero} del {elenco.emesso[:10]}, "
        f"{elenco.servizi} servizi qualificati"
    )
