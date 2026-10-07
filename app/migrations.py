"""Migrazioni dello schema di Minuta.

Ogni passo porta il database da una versione alla successiva dentro una
propria transazione: o il passo riesce per intero, o non lascia traccia.
Le migrazioni vanno solo avanti. Per tornare indietro si ripristina un backup.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    inspect,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine

from .db import VersioneSchema, adesso


class MigrationError(Exception):
    """Lo schema non può essere portato alla versione richiesta."""


def _passo_1(conn: Connection) -> None:
    """Schema iniziale: utenti, fascicoli, assegnazioni, registri, accessi."""
    meta = MetaData()
    orario = DateTime(timezone=True)
    Table(
        "utenti",
        meta,
        Column("id", Integer, primary_key=True),
        Column("nome_utente", String(40), nullable=False, unique=True),
        Column("nome", String(80), nullable=False),
        Column("hash_passphrase", String(255), nullable=False),
        Column("ruolo", String(20), nullable=False),
        Column("attivo", Boolean, nullable=False),
        Column("creato_il", orario, nullable=False),
        CheckConstraint(
            "ruolo IN ('avvocato', 'praticante', 'segreteria')",
            name="ck_utenti_ruolo",
        ),
    )
    Table(
        "fascicoli",
        meta,
        Column("id", Integer, primary_key=True),
        Column("codice", String(20), nullable=False, unique=True),
        Column("cliente", String(120), nullable=False),
        Column("materia", String(20), nullable=False),
        Column("oggetto", String(200), nullable=False),
        Column("avvocato_id", ForeignKey("utenti.id"), nullable=False),
        Column("stato", String(20), nullable=False),
        Column("versione", Integer, nullable=False),
        Column("creato_da_id", ForeignKey("utenti.id"), nullable=False),
        Column("creato_il", orario, nullable=False),
        Column("aggiornato_il", orario, nullable=False),
        CheckConstraint(
            "materia IN ('civile', 'tributario', 'penale')",
            name="ck_fascicoli_materia",
        ),
        CheckConstraint(
            "stato IN ('aperto', 'in_studio', 'deciso', 'chiuso')",
            name="ck_fascicoli_stato",
        ),
        CheckConstraint("versione >= 1", name="ck_fascicoli_versione"),
    )
    Table(
        "assegnazioni",
        meta,
        Column("fascicolo_id", ForeignKey("fascicoli.id"), primary_key=True),
        Column(
            "utente_id", ForeignKey("utenti.id"), primary_key=True, index=True
        ),
    )
    Table(
        "eventi",
        meta,
        Column("id", Integer, primary_key=True),
        Column("utente_id", ForeignKey("utenti.id"), nullable=True),
        Column(
            "fascicolo_id",
            ForeignKey("fascicoli.id"),
            nullable=True,
            index=True,
        ),
        Column("azione", String(40), nullable=False),
        Column("dettaglio", Text, nullable=False),
        Column("creato_il", orario, nullable=False),
    )
    Table(
        "uso_ai",
        meta,
        Column("id", Integer, primary_key=True),
        Column("quando", orario, nullable=False),
        Column("utente_id", ForeignKey("utenti.id"), nullable=False),
        Column(
            "fascicolo_id",
            ForeignKey("fascicoli.id"),
            nullable=True,
            index=True,
        ),
        Column("modello", String(80), nullable=False),
        Column("categorie", String(200), nullable=False),
        Column("scopo", String(200), nullable=False),
        Column("impronta", String(64), nullable=False),
        Column("caratteri", Integer, nullable=False),
        Column("controllo", String(200), nullable=False),
        Column("approvato_da_id", ForeignKey("utenti.id"), nullable=True),
        Column("token_in", Integer, nullable=True),
        Column("token_out", Integer, nullable=True),
        Column("costo_usd", Float, nullable=True),
    )
    Table(
        "sessioni",
        meta,
        Column("id", Integer, primary_key=True),
        Column("impronta", String(64), nullable=False, unique=True),
        Column(
            "utente_id", ForeignKey("utenti.id"), nullable=False, index=True
        ),
        Column("creata_il", orario, nullable=False),
        Column("scade_il", orario, nullable=False),
    )
    Table(
        "tentativi_falliti",
        meta,
        Column("id", Integer, primary_key=True),
        Column("nome_utente", String(40), nullable=False, index=True),
        Column("ip", String(64), nullable=False, index=True),
        Column("creato_il", orario, nullable=False, index=True),
    )
    Table(
        "versione_schema",
        meta,
        Column("id", Integer, primary_key=True),
        Column("versione", Integer, nullable=False),
        Column("applicata_il", orario, nullable=False),
    )
    meta.create_all(conn)


# Ogni nuova migrazione si aggiunge qui con il numero successivo.
PASSI: dict[int, tuple[str, Callable[[Connection], None]]] = {
    1: ("Schema iniziale", _passo_1),
}


def ultima() -> int:
    """La versione di schema che questo codice si aspetta."""
    return max(PASSI)


# [libro:migra]
def versione_attuale(conn: Connection) -> int:
    """La versione registrata nel database; 0 se il database è vuoto."""
    if not inspect(conn).has_table("versione_schema"):
        return 0
    query = select(VersioneSchema.versione).where(VersioneSchema.id == 1)
    return int(conn.execute(query).scalar() or 0)


def migra(engine: Engine) -> list[int]:
    """Applica in ordine i passi mancanti e restituisce quelli eseguiti."""
    with engine.connect() as conn:
        versione = versione_attuale(conn)
    if versione > ultima():
        raise MigrationError(
            f"Il database è alla versione {versione}, più recente del codice "
            f"({ultima()}): avvia una versione aggiornata di Minuta."
        )
    applicati = []
    for numero in range(versione + 1, ultima() + 1):
        _descrizione, passo = PASSI[numero]
        with engine.begin() as conn:  # un passo, una transazione
            passo(conn)
            _registra(conn, numero)
        applicati.append(numero)
    return applicati


# [/libro:migra]


def _registra(conn: Connection, numero: int) -> None:
    tabella = VersioneSchema.__table__
    valori = {"versione": numero, "applicata_il": adesso()}
    esiste = conn.execute(
        select(tabella.c.id).where(tabella.c.id == 1)
    ).first()
    if esiste:
        conn.execute(update(tabella).where(tabella.c.id == 1).values(**valori))
    else:
        conn.execute(insert(tabella).values(id=1, **valori))
