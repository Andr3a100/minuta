"""I dati di Minuta: tabelle, connessione, orari in UTC."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

RUOLI = ("avvocato", "praticante", "segreteria")
MATERIE = ("civile", "tributario", "penale")
STATI = ("aperto", "in_studio", "deciso", "chiuso")


def adesso() -> datetime:
    """L'orario corrente, sempre in UTC e sempre con il fuso indicato."""
    return datetime.now(UTC)


class OrarioUTC(TypeDecorator):
    """Salva ogni orario in UTC e lo restituisce sempre con il fuso.

    PostgreSQL conserva il fuso orario, SQLite no: questo tipo rende uguale
    il comportamento dei due database.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("orario senza fuso: usa adesso()")
        value = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    pass


# [libro:tabelle]
class Utente(Base):
    __tablename__ = "utenti"
    __table_args__ = (
        CheckConstraint(
            "ruolo IN ('avvocato', 'praticante', 'segreteria')",
            name="ck_utenti_ruolo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_utente: Mapped[str] = mapped_column(String(40), unique=True)
    nome: Mapped[str] = mapped_column(String(80))
    hash_passphrase: Mapped[str] = mapped_column(String(255))
    ruolo: Mapped[str] = mapped_column(String(20))
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    creato_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)


class Fascicolo(Base):
    __tablename__ = "fascicoli"
    __table_args__ = (
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codice: Mapped[str] = mapped_column(String(20), unique=True)
    cliente: Mapped[str] = mapped_column(String(120))
    materia: Mapped[str] = mapped_column(String(20))
    oggetto: Mapped[str] = mapped_column(String(200))
    avvocato_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"))
    stato: Mapped[str] = mapped_column(String(20), default="aperto")
    versione: Mapped[int] = mapped_column(Integer, default=1)
    creato_da_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"))
    creato_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)
    aggiornato_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)


class Assegnazione(Base):
    """Chi lavora su un fascicolo: solo queste persone lo vedono."""

    __tablename__ = "assegnazioni"

    fascicolo_id: Mapped[int] = mapped_column(
        ForeignKey("fascicoli.id"), primary_key=True
    )
    utente_id: Mapped[int] = mapped_column(
        ForeignKey("utenti.id"), primary_key=True, index=True
    )


class Evento(Base):
    """Il registro delle attività: chi ha fatto che cosa, e quando."""

    __tablename__ = "eventi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    utente_id: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"))
    fascicolo_id: Mapped[int | None] = mapped_column(
        ForeignKey("fascicoli.id"), index=True
    )
    azione: Mapped[str] = mapped_column(String(40))
    dettaglio: Mapped[str] = mapped_column(Text, default="{}")
    creato_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)


class UsoAI(Base):
    """Il registro dell'uso dell'AI della lezione 8, una voce per richiesta.

    Mai il testo inviato: la sua impronta e quanti caratteri erano.
    """

    __tablename__ = "uso_ai"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quando: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)
    utente_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"))
    fascicolo_id: Mapped[int | None] = mapped_column(
        ForeignKey("fascicoli.id"), index=True
    )
    modello: Mapped[str] = mapped_column(String(80))
    categorie: Mapped[str] = mapped_column(String(200))
    scopo: Mapped[str] = mapped_column(String(200))
    impronta: Mapped[str] = mapped_column(String(64))
    caratteri: Mapped[int] = mapped_column(Integer)
    controllo: Mapped[str] = mapped_column(String(200))
    approvato_da_id: Mapped[int | None] = mapped_column(
        ForeignKey("utenti.id")
    )
    token_in: Mapped[int | None] = mapped_column(Integer)
    token_out: Mapped[int | None] = mapped_column(Integer)
    costo_usd: Mapped[float | None] = mapped_column(Float)


# [/libro:tabelle]


# [libro:documento]
class Documento(Base):
    """Un documento del fascicolo (lezione 16). L'originale resta com'è
    arrivato nella cartella dei dati, con la sua impronta come nome; qui
    sta ciò che Minuta ne ha letto, e come."""

    __tablename__ = "documenti"
    __table_args__ = (
        UniqueConstraint("fascicolo_id", "impronta", name="uq_documenti"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fascicolo_id: Mapped[int] = mapped_column(
        ForeignKey("fascicoli.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    impronta: Mapped[str] = mapped_column(String(64))  # SHA-256
    byte: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(80))
    pagine: Mapped[int] = mapped_column(Integer)
    ottica: Mapped[bool] = mapped_column(Boolean)  # c'è una trascrizione
    nascosti: Mapped[int] = mapped_column(Integer)  # testi nascosti trovati
    integro: Mapped[bool | None] = mapped_column(Boolean)  # solo le buste
    certificato: Mapped[bool | None] = mapped_column(Boolean)
    lettura: Mapped[str] = mapped_column(Text)  # pagine e avvisi, in JSON
    caricato_da_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"))
    caricato_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)


# [/libro:documento]


# [libro:persone]
class PersonaFascicolo(Base):
    """Una persona o un soggetto dei documenti del fascicolo (lezione 17):
    l'elenco da cui parte la pseudonimizzazione, come chiede la lezione 4."""

    __tablename__ = "persone"
    __table_args__ = (
        UniqueConstraint("fascicolo_id", "nome", name="uq_persone"),
        CheckConstraint(
            "tipo IN ('PERSONA', 'SOGGETTO')", name="ck_persone_tipo"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fascicolo_id: Mapped[int] = mapped_column(
        ForeignKey("fascicoli.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(10))  # PERSONA o SOGGETTO
    ruolo: Mapped[str] = mapped_column(String(60))
    # Nessuno: il cliente, che la migrazione prende dal fascicolo.
    aggiunta_da_id: Mapped[int | None] = mapped_column(ForeignKey("utenti.id"))
    aggiunta_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)


class Segnaposto(Base):
    """La tabella dei segnaposto di un fascicolo: non lascia mai lo studio."""

    __tablename__ = "segnaposto"
    __table_args__ = (
        UniqueConstraint("fascicolo_id", "segno", name="uq_segnaposto"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fascicolo_id: Mapped[int] = mapped_column(
        ForeignKey("fascicoli.id"), index=True
    )
    segno: Mapped[str] = mapped_column(String(40))
    valore: Mapped[str] = mapped_column(String(200))


# [/libro:persone]


# [libro:scheda]
class Scheda(Base):
    """La scheda di un atto in arrivo (lezione 18): le righe proposte dal
    modello, con la pagina e i problemi trovati da Minuta, in JSON. Resta
    da verificare finché un avvocato non la conferma."""

    __tablename__ = "schede"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fascicolo_id: Mapped[int] = mapped_column(
        ForeignKey("fascicoli.id"), index=True
    )
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documenti.id"), index=True
    )
    righe: Mapped[str] = mapped_column(Text)
    uso_ai_id: Mapped[int] = mapped_column(ForeignKey("uso_ai.id"))
    preparata_da_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"))
    preparata_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)
    confermata_da_id: Mapped[int | None] = mapped_column(
        ForeignKey("utenti.id")
    )
    confermata_il: Mapped[datetime | None] = mapped_column(OrarioUTC)


# [/libro:scheda]


class Verifica(Base):
    """Le verifiche di un documento (lezione 20): le domande del suo tipo di
    atto, riempite da Minuta con i fatti e i controlli, e lo stato di
    ciascuna deciso dall'avvocato, in JSON."""

    __tablename__ = "verifiche"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fascicolo_id: Mapped[int] = mapped_column(
        ForeignKey("fascicoli.id"), index=True
    )
    documento_id: Mapped[int] = mapped_column(ForeignKey("documenti.id"))
    tipo: Mapped[str] = mapped_column(String(80))
    domande: Mapped[str] = mapped_column(Text)
    preparata_da_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"))
    preparata_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)


class Scadenza(Base):
    """Una scadenza calcolata da Minuta (lezione 19): il termine, la data di
    partenza presa dalla scheda confermata, i passaggi del calcolo con le
    loro norme. Resta da verificare finché un avvocato non la conferma; se
    le regole non bastano, la data manca e il motivo è scritto."""

    __tablename__ = "scadenze"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fascicolo_id: Mapped[int] = mapped_column(
        ForeignKey("fascicoli.id"), index=True
    )
    documento_id: Mapped[int] = mapped_column(ForeignKey("documenti.id"))
    scheda_id: Mapped[int] = mapped_column(ForeignKey("schede.id"))
    termine: Mapped[str] = mapped_column(String(120))
    norma: Mapped[str] = mapped_column(String(120))
    partenza: Mapped[date] = mapped_column(Date)
    scadenza: Mapped[date | None] = mapped_column(Date)
    passaggi: Mapped[str] = mapped_column(Text)  # in JSON
    da_decidere: Mapped[str | None] = mapped_column(Text)
    calcolata_da_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"))
    calcolata_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)
    confermata_da_id: Mapped[int | None] = mapped_column(
        ForeignKey("utenti.id")
    )
    confermata_il: Mapped[datetime | None] = mapped_column(OrarioUTC)


class SessioneAccesso(Base):
    __tablename__ = "sessioni"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    impronta: Mapped[str] = mapped_column(String(64), unique=True)
    utente_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"), index=True)
    creata_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)
    scade_il: Mapped[datetime] = mapped_column(OrarioUTC)


class TentativoFallito(Base):
    __tablename__ = "tentativi_falliti"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_utente: Mapped[str] = mapped_column(String(40), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    creato_il: Mapped[datetime] = mapped_column(
        OrarioUTC, default=adesso, index=True
    )


class VersioneSchema(Base):
    __tablename__ = "versione_schema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    versione: Mapped[int] = mapped_column(Integer)
    applicata_il: Mapped[datetime] = mapped_column(OrarioUTC, default=adesso)


# [libro:motore]
def make_engine(database_url: str) -> Engine:
    """Crea la connessione al database indicato da DATABASE_URL."""
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        _configura_sqlite(engine)
    return engine


def _configura_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _alla_connessione(connessione_dbapi, _record):
        # SQLite controlla le chiavi esterne solo se glielo chiedi (B7).
        cursore = connessione_dbapi.cursor()
        cursore.execute("PRAGMA foreign_keys=ON")
        cursore.close()
        # Le transazioni le apriamo noi, anche per le modifiche allo schema.
        connessione_dbapi.isolation_level = None

    @event.listens_for(engine, "begin")
    def _all_inizio(connessione):
        connessione.exec_driver_sql("BEGIN")


# [/libro:motore]


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
