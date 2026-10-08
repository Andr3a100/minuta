"""Comandi di amministrazione di Minuta.

Si usano dal terminale, dalla cartella del laboratorio:

    python -m app.manage migra
    python -m app.manage crea-utente sarti --ruolo avvocato \
        --nome "Elena Sarti"
    python -m app.manage disattiva irene
    python -m app.manage diagnosi
    python -m app.manage certificatori
    python -m app.manage carica 2026-071 documenti-di-prova/2026-071 --da irene
    python -m app.manage leggi documento.pdf
    python -m app.manage testo 2026-072 cartella-scansione.pdf
    python -m app.manage persona 2026-073 "Marco Bellini" \
        --ruolo "persona offesa" --da valli
    python -m app.manage anteprima 2026-073 avviso-415-bis.pdf.p7m
    python -m app.manage chiedi 2026-073 avviso-415-bis.pdf.p7m "..." \
        --da valli

Le passphrase non si scrivono mai sulla riga di comando, dove resterebbero
nella cronologia: il programma le chiede, oppure le legge da stdin.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import textwrap
from dataclasses import asdict
from datetime import date
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from minuta import certificatori
from minuta import documenti as motore
from minuta.archivio import leggi_indice
from minuta.domande import RispostaIlleggibile
from minuta.invio import SISTEMA
from minuta.scadenze import (
    TermineSconosciuto,
    calcola,
    carica_regole,
    in_lettere,
)
from minuta.scheda import Riga, SchedaIlleggibile
from minuta.verifiche import TipoSconosciuto, carica_domande

from .archivio import (
    ArchivioRifiutato,
    atti_dell_archivio,
    carica_atto,
    cerca_nell_archivio,
    puo_leggere,
)
from .config import ConfigError, leggi_file_env, load_settings
from .db import (
    RUOLI,
    Assegnazione,
    AttoArchivio,
    Documento,
    Evento,
    Fascicolo,
    PersonaFascicolo,
    RispostaFascicolo,
    Scadenza,
    Scheda,
    SessioneAccesso,
    UsoAI,
    Utente,
    Verifica,
    make_engine,
    make_session_factory,
)
from .documenti import (
    DocumentoRifiutato,
    carica,
    cartella_dati,
    descrivi,
    lettura_di,
    stato_elenco,
)
from .invio import (
    InvioBloccato,
    PersonaRifiutata,
    aggiungi_persona,
    cliente_in_elenco,
    domanda_sul_documento,
    modello_da,
    noti_del_fascicolo,
    prepara_domanda,
)
from .migrations import MigrationError, migra, ultima, versione_attuale
from .registro import RichiestaNonAmmessa
from .risposte import domanda_all_archivio, domanda_sul_fascicolo
from .scadenze import (
    ScadenzaRifiutata,
    calcola_scadenza,
    conferma_scadenza,
    ultima_scadenza,
)
from .schede import (
    SchedaRifiutata,
    conferma_scheda,
    prepara_scheda,
    righe_di,
    segnalate,
    togli_riga,
    ultima_scheda,
)
from .security import MIN_PASSPHRASE, hash_passphrase
from .verifiche import (
    VerificaRifiutata,
    decidi_domanda,
    prepara_verifiche,
    ultima_verifica,
)
from .web import registra_evento

NOME_UTENTE = re.compile(r"[a-z][a-z0-9._-]{2,39}")
CHIAVI = ("OPENAI_API_KEY", "MINUTA_API_KEY", "ANTHROPIC_API_KEY")


class CommandError(Exception):
    """Il comando non può essere eseguito: il messaggio spiega perché."""


# [libro:crea-utente]
def crea_utente(
    db: Session, nome_utente: str, ruolo: str, nome: str, passphrase: str
) -> Utente:
    """Crea un account. Le regole valgono anche per chi amministra."""
    nome_utente = nome_utente.strip().lower()
    if not NOME_UTENTE.fullmatch(nome_utente):
        raise CommandError(
            "Nome utente: da 3 a 40 caratteri tra lettere minuscole, "
            "cifre, punto, trattino e trattino basso; inizia con una lettera."
        )
    if ruolo not in RUOLI:
        raise CommandError("Ruolo non valido: " + ", ".join(RUOLI))
    nome = nome.strip()
    if not 1 <= len(nome) <= 80:
        raise CommandError("Il nome da mostrare va da 1 a 80 caratteri.")
    if db.scalar(select(Utente).where(Utente.nome_utente == nome_utente)):
        raise CommandError(f"L'utente {nome_utente} esiste già.")
    try:
        hash_salvato = hash_passphrase(passphrase)
    except ValueError as exc:
        raise CommandError(str(exc)) from None
    utente = Utente(
        nome_utente=nome_utente,
        nome=nome,
        hash_passphrase=hash_salvato,
        ruolo=ruolo,
    )
    db.add(utente)
    db.flush()
    registra_evento(
        db, None, None, "utente_creato", nome_utente=nome_utente, ruolo=ruolo
    )
    db.commit()
    return utente


# [/libro:crea-utente]


def imposta_attivo(db: Session, nome_utente: str, attivo: bool) -> Utente:
    """Disattiva o riattiva un account. Disattivare chiude le sessioni."""
    utente = db.scalar(select(Utente).where(Utente.nome_utente == nome_utente))
    if utente is None:
        raise CommandError(f"L'utente {nome_utente} non esiste.")
    utente.attivo = attivo
    if not attivo:
        db.execute(
            delete(SessioneAccesso).where(
                SessioneAccesso.utente_id == utente.id
            )
        )
    azione = "utente_riattivato" if attivo else "utente_disattivato"
    registra_evento(db, None, None, azione, nome_utente=nome_utente)
    db.commit()
    return utente


# I tre fascicoli della lezione 1: persone e fatti inventati per il libro.
PROVA = [
    (
        "2026-071",
        "Ristorazione Collinare S.r.l.",
        "civile",
        "Decreto ingiuntivo chiesto da Termocucine Secchia S.r.l., "
        "notificato il 21 settembre 2026",
        "Elena Sarti",
        "Irene",
    ),
    (
        "2026-072",
        "Ivo Marchetti",
        "tributario",
        "Cartella di pagamento per imposte di anni passati",
        "Paola Righi",
        None,
    ),
    (
        "2026-073",
        "Alessandro Riva",
        "penale",
        "Avviso di conclusione delle indagini dopo un infortunio sul lavoro",
        "Stefano Valli",
        None,
    ),
]


def crea_prova(db: Session, production: bool) -> int:
    """Crea i fascicoli di prova: mai in produzione, mai sopra dati veri."""
    if production:
        raise CommandError("I fascicoli di prova non si creano in produzione.")
    if db.scalar(select(func.count()).select_from(Fascicolo)):
        raise CommandError("L'archivio contiene già fascicoli: rifiutato.")
    persone = {u.nome: u for u in db.scalars(select(Utente))}
    avvocati = [u for u in persone.values() if u.ruolo == "avvocato"]
    if not avvocati:
        raise CommandError("Serve almeno un avvocato attivo.")
    segreteria = next(
        (u for u in persone.values() if u.ruolo == "segreteria"), None
    )
    for codice, cliente, materia, oggetto, avvocato, praticante in PROVA:
        titolare = persone.get(avvocato, avvocati[0])
        chi_apre = segreteria or titolare
        fascicolo = Fascicolo(
            codice=codice,
            cliente=cliente,
            materia=materia,
            oggetto=oggetto,
            avvocato_id=titolare.id,
            creato_da_id=chi_apre.id,
        )
        db.add(fascicolo)
        db.flush()
        assegnati = {chi_apre.id, titolare.id}
        if praticante in persone:
            assegnati.add(persone[praticante].id)
        for persona in sorted(assegnati):
            db.add(Assegnazione(fascicolo_id=fascicolo.id, utente_id=persona))
        cliente_in_elenco(db, fascicolo)
        registra_evento(
            db,
            chi_apre,
            fascicolo,
            "apertura",
            persone=sorted(assegnati),
            prova=True,
        )
    db.commit()
    return len(PROVA)


def leggi_passphrase(da_stdin: bool) -> str:
    if da_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    prima = getpass.getpass(
        f"Passphrase (almeno {MIN_PASSPHRASE} caratteri, non viene mostrata): "
    )
    seconda = getpass.getpass("Ripeti la passphrase: ")
    if prima != seconda:
        raise CommandError("Le due passphrase non coincidono.")
    return prima


def indirizzo_mascherato(url: str) -> str:
    """L'indirizzo del database senza la password: si può mostrare."""
    return make_url(url).render_as_string(hide_password=True)


def chiave_presente(file_env: Path = Path(".env")) -> str | None:
    """Il nome della variabile con la chiave del fornitore, se c'è."""
    valori = {**leggi_file_env(file_env), **os.environ}
    return next((nome for nome in CHIAVI if valori.get(nome)), None)


def costruisci_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.manage",
        description="Comandi di amministrazione di Minuta.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("migra", help="crea o aggiorna lo schema del database")
    crea = sub.add_parser("crea-utente", help="crea un account")
    crea.add_argument("nome_utente")
    crea.add_argument("--ruolo", required=True, choices=RUOLI)
    crea.add_argument("--nome", required=True, help="il nome da mostrare")
    crea.add_argument(
        "--passphrase-stdin",
        action="store_true",
        help="legge la passphrase da stdin (per gli script e le prove)",
    )
    for nome, testo in (
        ("disattiva", "disattiva un account"),
        ("riattiva", "riattiva un account"),
    ):
        comando = sub.add_parser(nome, help=testo)
        comando.add_argument("nome_utente")
    sub.add_parser("utenti", help="elenca gli account")
    sub.add_parser("prova", help="crea i tre fascicoli di prova del libro")
    sub.add_parser("diagnosi", help="mostra la configurazione senza segreti")
    sub.add_parser(
        "certificatori", help="scarica l'elenco dei certificatori di AgID"
    )
    caricamento = sub.add_parser(
        "carica", help="aggiunge documenti a un fascicolo"
    )
    caricamento.add_argument("codice", help="il codice del fascicolo")
    caricamento.add_argument(
        "percorsi", nargs="+", help="file, o cartelle di file"
    )
    caricamento.add_argument(
        "--da", required=True, help="chi carica: un utente del fascicolo"
    )
    lettura = sub.add_parser(
        "leggi", help="mostra che cosa Minuta legge in un file, senza salvarlo"
    )
    lettura.add_argument("percorsi", nargs="+")
    testo = sub.add_parser("testo", help="il testo letto da un documento")
    testo.add_argument("codice")
    testo.add_argument("nome")
    sub.add_parser("persone", help="l'elenco delle persone di un fascicolo")
    sub.choices["persone"].add_argument("codice")
    persona = sub.add_parser("persona", help="aggiunge una persona all'elenco")
    persona.add_argument("codice")
    persona.add_argument("nome")
    persona.add_argument("--ruolo", required=True)
    persona.add_argument(
        "--soggetto", action="store_true", help="una società o un ente"
    )
    persona.add_argument("--da", required=True, help="chi la aggiunge")
    anteprima = sub.add_parser(
        "anteprima", help="che cosa partirebbe verso il modello, e i controlli"
    )
    anteprima.add_argument("codice")
    anteprima.add_argument("nome", help="il nome del documento")
    anteprima.add_argument("--domanda", default="")
    anteprima.add_argument("--da", required=True, help="chi fa la domanda")
    domanda = sub.add_parser("chiedi", help="una domanda su un documento")
    domanda.add_argument("codice")
    domanda.add_argument("nome", help="il nome del documento")
    domanda.add_argument("domanda")
    domanda.add_argument("--da", required=True, help="chi fa la domanda")
    domanda.add_argument(
        "--verbale", help="salva lo scambio in un file JSON, per il libro"
    )
    scheda = sub.add_parser("scheda", help="la scheda di un atto in arrivo")
    scheda.add_argument("codice")
    scheda.add_argument("nome", help="il nome del documento")
    scheda.add_argument("--da", required=True, help="chi la prepara")
    scheda.add_argument(
        "--verbale", help="salva lo scambio in un file JSON, per il libro"
    )
    togli = sub.add_parser("togli-riga", help="toglie una riga dalla scheda")
    togli.add_argument("codice")
    togli.add_argument("nome", help="il nome del documento")
    togli.add_argument("numero", type=int, help="il numero della riga")
    togli.add_argument("--da", required=True, help="chi la toglie")
    conferma = sub.add_parser("conferma-scheda", help="conferma la scheda")
    conferma.add_argument("codice")
    conferma.add_argument("nome", help="il nome del documento")
    conferma.add_argument("--da", required=True, help="l'avvocato")
    sub.add_parser("termini", help="le regole dei termini, con le norme")
    scadenza = sub.add_parser("scadenza", help="calcola una scadenza")
    scadenza.add_argument("codice")
    scadenza.add_argument("nome", help="il documento con la scheda")
    scadenza.add_argument("--termine", required=True)
    scadenza.add_argument("--da", required=True, help="chi la calcola")
    conferma_s = sub.add_parser(
        "conferma-scadenza", help="conferma l'ultima scadenza del documento"
    )
    conferma_s.add_argument("codice")
    conferma_s.add_argument("nome", help="il documento con la scheda")
    conferma_s.add_argument("--da", required=True, help="l'avvocato")
    prova = sub.add_parser(
        "calcola-termine", help="prova il calcolo su una data, senza salvare"
    )
    prova.add_argument("termine")
    prova.add_argument("partenza", type=date.fromisoformat, help="AAAA-MM-GG")
    sub.add_parser("domande", help="le domande delle verifiche, per tipo")
    verifiche = sub.add_parser("verifiche", help="le verifiche di un atto")
    verifiche.add_argument("codice")
    verifiche.add_argument("nome", help="il nome del documento")
    verifiche.add_argument("--tipo", required=True, help="il tipo di atto")
    verifiche.add_argument("--da", required=True, help="chi le prepara")
    stato = sub.add_parser("stato-verifica", help="lo stato di una domanda")
    stato.add_argument("codice")
    stato.add_argument("nome", help="il nome del documento")
    stato.add_argument("numero", type=int, help="il numero della domanda")
    stato.add_argument(
        "stato", choices=["aperta", "verificata", "non-pertinente"]
    )
    stato.add_argument("--da", required=True, help="l'avvocato")
    sul = sub.add_parser("domanda", help="una domanda su tutto il fascicolo")
    sul.add_argument("codice")
    sul.add_argument("domanda")
    sul.add_argument("--da", required=True, help="chi fa la domanda")
    sul.add_argument(
        "--archivio",
        action="store_true",
        help="chiede agli atti dell'archivio, non ai documenti del fascicolo",
    )
    filtri(sul)
    sul.add_argument(
        "--verbale", help="salva lo scambio in un file JSON, per il libro"
    )
    carica_a = sub.add_parser(
        "carica-archivio", help="carica atti firmati nell'archivio"
    )
    carica_a.add_argument("percorsi", nargs="+", help="file o cartelle")
    carica_a.add_argument(
        "--indice", help="il CSV con le persone di ogni atto (indice.csv)"
    )
    carica_a.add_argument("--da", required=True, help="l'avvocato")
    elenco = sub.add_parser("archivio", help="gli atti dell'archivio")
    elenco.add_argument("--da", required=True, help="chi lo consulta")
    cerca = sub.add_parser("cerca", help="cerca negli atti dell'archivio")
    cerca.add_argument("parole")
    filtri(cerca)
    cerca.add_argument("--da", required=True, help="chi cerca")
    return parser


def filtri(comando: argparse.ArgumentParser) -> None:
    """Tipo, autore e periodo: gli stessi per cercare e per chiedere."""
    comando.add_argument("--tipo", help="il tipo di atto (basta l'inizio)")
    comando.add_argument("--autore", help="il nome utente dell'avvocato")
    comando.add_argument("--dal", type=date.fromisoformat, help="AAAA-MM-GG")
    comando.add_argument("--al", type=date.fromisoformat, help="AAAA-MM-GG")


def documento_del_fascicolo(db: Session, codice: str, nome: str):
    fascicolo = db.scalar(select(Fascicolo).where(Fascicolo.codice == codice))
    if fascicolo is None:
        raise CommandError(f"Il fascicolo {codice} non esiste.")
    documento = db.scalar(
        select(Documento).where(
            Documento.fascicolo_id == fascicolo.id, Documento.nome == nome
        )
    )
    if documento is None:
        raise CommandError(f"Nel fascicolo {codice} non c'è {nome}.")
    return fascicolo, documento


def stampa_persone(db: Session, codice: str) -> None:
    fascicolo = db.scalar(select(Fascicolo).where(Fascicolo.codice == codice))
    if fascicolo is None:
        raise CommandError(f"Il fascicolo {codice} non esiste.")
    elenco = list(
        db.scalars(
            select(PersonaFascicolo)
            .where(PersonaFascicolo.fascicolo_id == fascicolo.id)
            .order_by(PersonaFascicolo.id)
        )
    )
    print(f"Persone del fascicolo {codice}:")
    for persona in elenco:
        tipo = " (società o ente)" if persona.tipo == "SOGGETTO" else ""
        print(f"  {persona.nome}{tipo}: {persona.ruolo}")
    nomi = {p.nome for p in elenco}
    studio = [n for n in noti_del_fascicolo(db, fascicolo) if n not in nomi]
    if studio:
        print("E dello studio, perché ci lavorano: " + ", ".join(studio))


def stampa_controlli(preparato, noti: dict[str, str]) -> None:
    print(f"Nomi noti a Minuta: {len(noti)} ({', '.join(noti)})")
    print("Fughe: " + (", ".join(preparato.fughe) or "nessuna"))
    print("Nomi fuori elenco: " + (", ".join(preparato.nomi) or "nessuno"))
    print("Testo nascosto: " + ("; ".join(preparato.nascosto) or "nessuno"))
    if preparato.salute:
        print("Dati sulla salute: " + ", ".join(preparato.salute))


def file_da(percorsi: list[str]) -> list[Path]:
    """I file indicati; di una cartella, i file che contiene, per nome."""
    trovati = []
    for percorso in map(Path, percorsi):
        if percorso.is_dir():
            trovati += sorted(
                f
                for f in percorso.iterdir()
                if f.is_file() and not f.name.startswith(".")
            )
        elif percorso.is_file():
            trovati.append(percorso)
        else:
            raise CommandError(f"{percorso}: il file non esiste.")
    return trovati


GIORNI = (
    "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre "
    "ottobre novembre dicembre"
).split()


def giorno(iso: str) -> str:
    anno, mese, giorno_del_mese = (int(n) for n in iso[:10].split("-"))
    return f"{giorno_del_mese} {GIORNI[mese - 1]} {anno}"


def scarica_elenco(settings) -> None:
    try:
        elenco = certificatori.scarica(cartella_dati(settings))
    except OSError as exc:
        raise CommandError(f"Elenco non scaricato: {exc}") from None
    print(
        f"Elenco dei certificatori di AgID n. {elenco.numero}, emesso il "
        f"{giorno(elenco.emesso)}: {elenco.servizi} servizi qualificati "
        f"di {elenco.certificatori} certificatori."
    )


def fascicolo_e_utente(db: Session, codice: str, nome_utente: str):
    fascicolo = db.scalar(select(Fascicolo).where(Fascicolo.codice == codice))
    if fascicolo is None:
        raise CommandError(f"Il fascicolo {codice} non esiste.")
    utente = db.scalar(select(Utente).where(Utente.nome_utente == nome_utente))
    if utente is None or not utente.attivo:
        raise CommandError(f"{nome_utente}: utente inesistente o non attivo.")
    lavora = db.scalar(
        select(Assegnazione).where(
            Assegnazione.fascicolo_id == fascicolo.id,
            Assegnazione.utente_id == utente.id,
        )
    )
    if lavora is None:  # le stesse regole del browser
        raise CommandError(f"{nome_utente} non lavora al fascicolo {codice}.")
    return fascicolo, utente


def carica_file(db: Session, settings, args) -> int:
    fascicolo, utente = fascicolo_e_utente(db, args.codice, args.da)
    print(f"Fascicolo {fascicolo.codice}, caricati da {utente.nome}:")
    rifiutati = 0
    for percorso in file_da(args.percorsi):
        try:
            _documento, lettura = carica(
                db,
                settings,
                utente,
                fascicolo,
                percorso.name,
                percorso.read_bytes(),
            )
        except (DocumentoRifiutato, motore.DocumentoNonLeggibile) as exc:
            db.rollback()
            print(f"{percorso.name}: rifiutato. {exc}")
            rifiutati += 1
            continue
        print("\n".join(descrivi(lettura)))
    return 1 if rifiutati else 0


def stampa_testo(db: Session, codice: str, nome: str) -> None:
    documento = db.scalar(
        select(Documento)
        .join(Fascicolo, Documento.fascicolo_id == Fascicolo.id)
        .where(Fascicolo.codice == codice, Documento.nome == nome)
    )
    if documento is None:
        raise CommandError(f"Nel fascicolo {codice} non c'è {nome}.")
    for pagina in lettura_di(documento)["pagine"]:
        titolo = f"pagina {pagina['numero']}"
        if pagina["ottica"]:
            titolo += ", lettura ottica"
            if pagina["risoluzione"]:
                titolo += f" a {pagina['risoluzione']} punti per pollice"
        print(f"--- {titolo} ---")
        print(pagina["testo"])


def main(argv: list[str] | None = None) -> int:
    args = costruisci_parser().parse_args(argv)
    # Le regole dei termini non chiedono configurazione né database.
    if args.comando == "termini":
        stampa_regole(carica_regole())
        return 0
    if args.comando == "domande":
        stampa_domande(carica_domande())
        return 0
    if args.comando == "calcola-termine":
        try:
            calcolo = calcola(args.termine, args.partenza, carica_regole())
        except TermineSconosciuto as exc:
            print(str(exc), file=sys.stderr)
            return 1
        stampa_calcolo(calcolo)
        return 0
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configurazione non valida: {exc}", file=sys.stderr)
        return 2
    engine = make_engine(settings.database_url)
    try:
        if args.comando == "migra":
            applicati = migra(engine)
            if applicati:
                passi = ", ".join(str(n) for n in applicati)
                print(f"Schema aggiornato: passi applicati {passi}.")
            print(f"Schema alla versione {ultima()}.")
            return 0
        if args.comando == "diagnosi":
            return diagnosi(settings, engine)
        if args.comando == "certificatori":
            scarica_elenco(settings)
            return 0
        if args.comando == "leggi":
            for percorso in file_da(args.percorsi):
                lettura = motore.leggi(
                    percorso.name,
                    percorso.read_bytes(),
                    cartella_dati(settings),
                )
                print("\n".join(descrivi(lettura)))
            return 0

        with engine.connect() as conn:
            versione = versione_attuale(conn)
        if versione != ultima():
            raise CommandError(
                f"Schema alla versione {versione}, attesa {ultima()}: "
                "esegui prima  python -m app.manage migra"
            )
        with make_session_factory(engine)() as db:
            if args.comando == "crea-utente":
                passphrase = leggi_passphrase(args.passphrase_stdin)
                utente = crea_utente(
                    db, args.nome_utente, args.ruolo, args.nome, passphrase
                )
                print(
                    f"Creato l'utente {utente.nome_utente} ({utente.ruolo})."
                )
            elif args.comando in ("disattiva", "riattiva"):
                attivo = args.comando == "riattiva"
                utente = imposta_attivo(db, args.nome_utente, attivo)
                stato = "attivo" if attivo else "disattivato"
                print(f"Utente {utente.nome_utente}: {stato}.")
            elif args.comando == "utenti":
                for u in db.scalars(
                    select(Utente).order_by(Utente.nome_utente)
                ):
                    stato = "attivo" if u.attivo else "disattivato"
                    colonne = f"{u.nome_utente:<10} {u.ruolo:<11} {stato:<12}"
                    print(f"{colonne} {u.nome}")
            elif args.comando == "prova":
                quanti = crea_prova(db, settings.production)
                print(f"Creati {quanti} fascicoli di prova.")
            elif args.comando == "carica":
                return carica_file(db, settings, args)
            elif args.comando == "testo":
                stampa_testo(db, args.codice, args.nome)
            elif args.comando == "persone":
                stampa_persone(db, args.codice)
            elif args.comando == "persona":
                fascicolo, utente = fascicolo_e_utente(
                    db, args.codice, args.da
                )
                persona = aggiungi_persona(
                    db, utente, fascicolo, args.nome, args.ruolo, args.soggetto
                )
                print(
                    f"Aggiunta all'elenco di {fascicolo.codice}: "
                    f"{persona.nome} ({persona.ruolo})."
                )
            elif args.comando == "anteprima":
                return anteprima(db, args)
            elif args.comando == "chiedi":
                return chiedi_al_modello(db, settings, args)
            elif args.comando == "scheda":
                return scheda_dell_atto(db, settings, args)
            elif args.comando == "togli-riga":
                togli_dalla_scheda(db, args)
            elif args.comando == "conferma-scheda":
                conferma_dalla_riga_di_comando(db, args)
            elif args.comando == "scadenza":
                scadenza_dalla_scheda(db, args)
            elif args.comando == "conferma-scadenza":
                conferma_scadenza_da_riga(db, args)
            elif args.comando == "verifiche":
                verifiche_del_documento(db, args)
            elif args.comando == "stato-verifica":
                stato_di_una_verifica(db, args)
            elif args.comando == "domanda":
                return domanda_al_fascicolo(db, settings, args)
            elif args.comando == "carica-archivio":
                return carica_l_archivio(db, settings, args)
            elif args.comando == "archivio":
                stampa_archivio(db, args)
            elif args.comando == "cerca":
                cerca_dalla_riga(db, args)
        return 0
    except (
        ArchivioRifiutato,
        CommandError,
        MigrationError,
        motore.DocumentoNonLeggibile,
        PersonaRifiutata,
        RichiestaNonAmmessa,
        SchedaRifiutata,
        ScadenzaRifiutata,
        TermineSconosciuto,
        VerificaRifiutata,
        TipoSconosciuto,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()


def chi_puo_chiedere(db: Session, args):
    """Le regole del browser: lavora al fascicolo, e non è la segreteria."""
    fascicolo, documento = documento_del_fascicolo(db, args.codice, args.nome)
    _fascicolo, utente = fascicolo_e_utente(db, args.codice, args.da)
    if utente.ruolo == "segreteria":
        raise CommandError("La segreteria non fa richieste al modello.")
    return utente, fascicolo, documento


def anteprima(db: Session, args) -> int:
    utente, fascicolo, documento = chi_puo_chiedere(db, args)
    preparato, _persone = prepara_domanda(
        db, utente, fascicolo, documento, args.domanda
    )
    print(f"Fascicolo {fascicolo.codice} · {documento.nome}")
    stampa_controlli(preparato, noti_del_fascicolo(db, fascicolo))
    if preparato.bloccato:
        print(
            "Invio BLOCCATO: niente parte finché resta qualcosa da nascondere."
        )
    print("--- il testo che partirebbe ---")
    print(preparato.testo)
    return 1 if preparato.bloccato else 0


def chiedi_al_modello(db: Session, settings, args) -> int:
    utente, fascicolo, documento = chi_puo_chiedere(db, args)
    print(f"Fascicolo {fascicolo.codice} · {documento.nome} · {utente.nome}")
    try:
        esito = domanda_sul_documento(
            db,
            utente,
            fascicolo,
            documento,
            args.domanda,
            modello_da(settings),
        )
    except InvioBloccato as blocco:
        stampa_controlli(blocco.preparato, noti_del_fascicolo(db, fascicolo))
        print(
            "Invio BLOCCATO: niente parte finché resta qualcosa da nascondere."
        )
        return 1
    voce = esito.voce
    print(f"Controllo: {voce.controllo}")
    if esito.preparato.salute:
        print(
            "Dati sulla salute inviati: " + ", ".join(esito.preparato.salute)
        )
    if esito.preparato.nascosto:
        print("Testo nascosto inviato: " + "; ".join(esito.preparato.nascosto))
    print("--- la risposta, con i nomi rimessi nello studio ---")
    print(esito.risposta)
    if esito.sconosciuti:
        print(
            "Segnaposto inventati dal modello: " + ", ".join(esito.sconosciuti)
        )
    print(riga_del_registro(voce))
    if args.verbale:
        Path(args.verbale).write_text(
            json.dumps(
                {
                    "quando": voce.quando.isoformat(),
                    "modello": voce.modello,
                    "domanda": args.domanda,
                    "sistema": SISTEMA,
                    "inviato": esito.preparato.testo,
                    "arrivata": esito.arrivata,
                    "ricomposta": esito.risposta,
                    "token_in": voce.token_in,
                    "token_out": voce.token_out,
                    "costo_usd": voce.costo_usd,
                    "controllo": voce.controllo,
                    "categorie": voce.categorie,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            "utf-8",
        )
    return 0


def riga_del_registro(voce) -> str:
    costo = (
        f"{voce.costo_usd:.4f} dollari"
        if voce.costo_usd is not None
        else "non stimato"
    )
    return (
        f"Registro dell'uso dell'AI: voce n. {voce.id}, {voce.modello}, "
        f"{voce.caratteri} caratteri, token {voce.token_in} + "
        f"{voce.token_out}, costo {costo}"
    )


def righe_stampate(righe: list[Riga]) -> list[str]:
    """La scheda come la mostra il terminale: ogni riga con la sua voce e
    la sua pagina, e sotto i problemi che Minuta vi ha trovato."""
    stampa = []
    for n, riga in enumerate(righe, start=1):
        if riga.tolta_da:
            testa = f"{n:2}. tolta da {riga.tolta_da}: {riga.testo}"
        else:
            dove = "" if riga.pagina is None else f" · pagina {riga.pagina}"
            testa = f"{n:2}. {riga.voce}{dove} · {riga.testo}"
        stampa += textwrap.wrap(testa, 79, subsequent_indent="    ")
        for problema in [] if riga.tolta_da else riga.problemi:
            stampa += textwrap.wrap(
                problema,
                79,
                initial_indent="    ! ",
                subsequent_indent="      ",
            )
    return stampa


def scheda_dell_atto(db: Session, settings, args) -> int:
    utente, fascicolo, documento = chi_puo_chiedere(db, args)
    print(f"Fascicolo {fascicolo.codice} · {documento.nome} · {utente.nome}")
    try:
        esito = prepara_scheda(
            db, utente, fascicolo, documento, modello_da(settings)
        )
    except InvioBloccato as blocco:
        stampa_controlli(blocco.preparato, noti_del_fascicolo(db, fascicolo))
        print(
            "Invio BLOCCATO: niente parte finché resta qualcosa da nascondere."
        )
        return 1
    except SchedaIlleggibile as exc:
        print(f"La risposta non è una scheda: {exc}.")
        print("La richiesta è partita, e la sua voce resta nel registro.")
        return 1
    print(f"Controllo: {esito.voce.controllo}")
    print("--- la scheda, da verificare ---")
    stampa = righe_stampate(esito.righe)
    print("\n".join(stampa))
    restano = segnalate(esito.righe)
    print("Righe segnalate: " + (", ".join(map(str, restano)) or "nessuna"))
    print(riga_del_registro(esito.voce))
    if args.verbale:
        voce = esito.voce
        Path(args.verbale).write_text(
            json.dumps(
                {
                    "quando": voce.quando.isoformat(),
                    "modello": voce.modello,
                    "documento": documento.nome,
                    "sistema": SISTEMA,
                    "inviato": esito.preparato.testo,
                    "arrivata": esito.arrivata,
                    "righe": [asdict(r) for r in esito.righe],
                    "stampa": "\n".join(stampa),
                    "token_in": voce.token_in,
                    "token_out": voce.token_out,
                    "costo_usd": voce.costo_usd,
                    "controllo": voce.controllo,
                    "categorie": voce.categorie,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            "utf-8",
        )
    return 0


def scheda_esistente(db: Session, args):
    fascicolo, documento = documento_del_fascicolo(db, args.codice, args.nome)
    _fascicolo, utente = fascicolo_e_utente(db, args.codice, args.da)
    scheda = ultima_scheda(db, documento)
    if scheda is None:
        raise CommandError(f"{documento.nome} non ha ancora una scheda.")
    return utente, fascicolo, documento, scheda


def togli_dalla_scheda(db: Session, args) -> None:
    utente, fascicolo, _documento, scheda = scheda_esistente(db, args)
    riga = togli_riga(db, utente, fascicolo, scheda, args.numero)
    print(f"Riga {args.numero} tolta da {utente.nome}: {riga.testo}")


def conferma_dalla_riga_di_comando(db: Session, args) -> None:
    utente, fascicolo, documento, scheda = scheda_esistente(db, args)
    conferma_scheda(db, utente, fascicolo, scheda)
    print(f"Scheda di {documento.nome} confermata da {utente.nome}:")
    print("\n".join(righe_stampate(righe_di(scheda))))


def stampa_regole(regole: dict) -> None:
    print("Le regole di config/termini.json:")
    for t in regole["termini"]:
        validita = ""
        if "dal" in t:
            validita = f", dal {t['dal']}"
        if "fino_al" in t:
            validita = f", fino al {t['fino_al']}"
        riga = (
            f"{t['nome']} ({t['materia']}): {t['giorni']} giorni dalla "
            f"{t['da']}, {t['norma']}{validita}, letta il {t['letta_il']}"
        )
        if t.get("rinvio") == "da verificare":
            riga += "; rinvio al c.p.c. da verificare"
        print(
            "\n".join(
                textwrap.wrap(
                    riga, 79, initial_indent="  ", subsequent_indent="    "
                )
            )
        )
    computo = regole["computo"]
    conta = (
        f"Si contano: nel civile con l'{computo['civile']['norma']}, che "
        f"sposta anche la scadenza del sabato; nel penale con "
        f"l'{computo['penale']['norma']}"
    )
    print("\n".join(textwrap.wrap(conta, 79, subsequent_indent="  ")))
    print(f"Agosto: {regole['sospensione_feriale']['norma']}.")
    norme = "; ".join(n["norma"] for n in regole["festivi"]["norme"])
    print(
        "\n".join(
            textwrap.wrap(f"Festivi: {norme}.", 79, subsequent_indent="  ")
        )
    )


def stampa_calcolo(calcolo, salvato: bool = False) -> None:
    print(f"Termine: {calcolo.termine}")
    for passaggio in calcolo.passaggi:
        print(
            "\n".join(
                textwrap.wrap(
                    passaggio,
                    79,
                    initial_indent="  · ",
                    subsequent_indent="    ",
                )
            )
        )
    if calcolo.scadenza is None:
        motivo = f"Decide l'avvocato: {calcolo.da_decidere}."
        print("\n".join(textwrap.wrap(motivo, 79, subsequent_indent="  ")))
    else:
        stato = ", da verificare" if salvato else ""
        print(f"Scadenza: {in_lettere(calcolo.scadenza)}{stato}.")


def scadenza_dalla_scheda(db: Session, args) -> None:
    fascicolo, documento = documento_del_fascicolo(db, args.codice, args.nome)
    _fascicolo, utente = fascicolo_e_utente(db, args.codice, args.da)
    _scadenza, calcolo, riga = calcola_scadenza(
        db, utente, fascicolo, documento, args.termine
    )
    print(f"Fascicolo {fascicolo.codice} · {documento.nome} · {utente.nome}")
    print(
        f"Partenza dalla scheda, riga {riga}: {in_lettere(calcolo.partenza)}"
    )
    stampa_calcolo(calcolo, salvato=True)


def conferma_scadenza_da_riga(db: Session, args) -> None:
    fascicolo, documento = documento_del_fascicolo(db, args.codice, args.nome)
    _fascicolo, utente = fascicolo_e_utente(db, args.codice, args.da)
    scadenza = ultima_scadenza(db, documento)
    if scadenza is None:
        raise CommandError(f"{documento.nome} non ha ancora una scadenza.")
    conferma_scadenza(db, utente, fascicolo, scadenza)
    print(
        f"Scadenza confermata da {utente.nome}: {scadenza.termine}, "
        f"{in_lettere(scadenza.scadenza)}."
    )


def a_capo(testo: str, primo: str, altri: str) -> list[str]:
    return textwrap.wrap(
        testo, 79, initial_indent=primo, subsequent_indent=altri
    )


def stampa_domande(domande: dict) -> None:
    print("Le domande di config/verifiche.json:")
    for tipo, elenco in domande["tipi"].items():
        print(tipo)
        for n, d in enumerate(elenco, start=1):
            if d.get("norma"):
                da = f"{d['norma']}, letta il {d['letta_il']}"
            elif d.get("controllo") == "somme":
                da = "Minuta rifà le somme"
            elif d.get("controllo") == "scadenze":
                da = "Minuta riporta le scadenze del documento"
            else:
                da = "dalla scheda: " + ", ".join(d.get("voci", []))
            print(
                "\n".join(
                    a_capo(f"{d['domanda']} ({da})", f"  {n:2}. ", "      ")
                )
            )


def righe_delle_verifiche(domande: list[dict]) -> list[str]:
    """Le verifiche come le mostra il terminale: per ogni domanda lo stato,
    dove guardare, la norma, i fatti e i controlli; «!» dove qualcosa
    non torna."""
    stampa = []
    for n, d in enumerate(domande, start=1):
        stato = d["stato"] + (f", {d['deciso_da']}" if d["deciso_da"] else "")
        stampa += a_capo(f"{d['domanda']} [{stato}]", f"{n:2}. ", "    ")
        stampa += a_capo(f"dove guardare: {d['dove']}", "    ", "      ")
        if d["norma"]:
            norma = f"norma: {d['norma']}, letta il {d['letta_il']}"
            stampa += a_capo(norma, "    ", "      ")
        for voce in d["fatti"] + d["controlli"]:
            if voce.startswith("! "):
                stampa += a_capo(voce[2:], "    ! ", "      ")
            else:
                stampa += a_capo(voce, "    · ", "      ")
    return stampa


def verifiche_del_documento(db: Session, args) -> None:
    fascicolo, documento = documento_del_fascicolo(db, args.codice, args.nome)
    _fascicolo, utente = fascicolo_e_utente(db, args.codice, args.da)
    verifica = prepara_verifiche(db, utente, fascicolo, documento, args.tipo)
    print(f"Verifiche di {documento.nome} · {verifica.tipo} · {utente.nome}")
    print("\n".join(righe_delle_verifiche(json.loads(verifica.domande))))


def stato_di_una_verifica(db: Session, args) -> None:
    fascicolo, documento = documento_del_fascicolo(db, args.codice, args.nome)
    _fascicolo, utente = fascicolo_e_utente(db, args.codice, args.da)
    verifica = ultima_verifica(db, documento)
    if verifica is None:
        raise CommandError(f"{documento.nome} non ha ancora le verifiche.")
    stato = args.stato.replace("-", " ")
    domanda = decidi_domanda(
        db, utente, fascicolo, verifica, args.numero, stato
    )
    print(f"Domanda {args.numero}, {stato}: {domanda['domanda']}")


def righe_della_risposta(frasi) -> list[str]:
    """Ogni frase con la sua citazione, e sotto i problemi che Minuta vi ha
    trovato."""
    stampa = []
    for n, frase in enumerate(frasi, start=1):
        stampa += a_capo(frase.testo, f"{n:2}. ", "    ")
        dove = f"{frase.documento}, pagina {frase.pagina}"
        stampa += a_capo(f"{dove}: «{frase.citazione}»", "    ", "      ")
        for problema in frase.problemi:
            stampa += a_capo(problema, "    ! ", "      ")
    return stampa


def domanda_al_fascicolo(db: Session, settings, args) -> int:
    fascicolo, utente = fascicolo_e_utente(db, args.codice, args.da)
    filtrata = args.tipo or args.autore or args.dal or args.al
    if filtrata and not args.archivio:
        raise CommandError("Tipo, autore e periodo valgono con --archivio.")
    try:
        if args.archivio:
            esito = domanda_all_archivio(
                db,
                utente,
                fascicolo,
                args.domanda,
                modello_da(settings),
                args.tipo,
                args.autore,
                args.dal,
                args.al,
            )
        else:
            esito = domanda_sul_fascicolo(
                db, utente, fascicolo, args.domanda, modello_da(settings)
            )
    except InvioBloccato as blocco:
        print(f"Fascicolo {fascicolo.codice} · {utente.nome}")
        stampa_controlli(blocco.preparato, noti_del_fascicolo(db, fascicolo))
        print(
            "Invio BLOCCATO: niente parte finché resta qualcosa da nascondere."
        )
        return 1
    except RispostaIlleggibile as exc:
        print(f"La risposta non è nella forma chiesta: {exc}.")
        print("La richiesta è partita, e la sua voce resta nel registro.")
        return 1
    print(f"Fascicolo {fascicolo.codice} · {utente.nome}")
    if not esito.passi:
        print(
            "\n".join(a_capo(f"Risposta di Minuta: {esito.manca}.", "", "  "))
        )
        print("Nessuna richiesta è partita.")
        return 0
    scelti = "; ".join(
        f"{p.documento}, pagina {p.pagina}" for p in esito.passi
    )
    dall_archivio = esito.fonte == "archivio"
    mandati = (
        "Passi mandati, dall'archivio" if dall_archivio else "Passi mandati"
    )
    print("\n".join(a_capo(f"{mandati}: {scelti}", "", "  ")))
    print("\n".join(a_capo(f"Controllo: {esito.voce.controllo}", "", "  ")))
    if dall_archivio:
        print(
            "--- la risposta: atti di altri clienti, i nomi restano nascosti ---"
        )
    else:
        print("--- la risposta, con i nomi rimessi nello studio ---")
    stampa = righe_della_risposta(esito.frasi)
    if esito.manca:
        stampa = a_capo(f"Nei passi mandati non c'è: {esito.manca}", "", "  ")
    print("\n".join(stampa))
    segnalate = [str(n) for n, f in enumerate(esito.frasi, 1) if f.problemi]
    print("Citazioni segnalate: " + (", ".join(segnalate) or "nessuna"))
    print(riga_del_registro(esito.voce))
    if args.verbale:
        voce = esito.voce
        Path(args.verbale).write_text(
            json.dumps(
                {
                    "quando": voce.quando.isoformat(),
                    "modello": voce.modello,
                    "domanda": args.domanda,
                    "sistema": SISTEMA,
                    "inviato": esito.preparato.testo,
                    "arrivata": esito.arrivata,
                    "fonte": esito.fonte,
                    "passi": [(p.documento, p.pagina) for p in esito.passi],
                    "frasi": [asdict(f) for f in esito.frasi],
                    "manca": esito.manca,
                    "stampa": "\n".join(stampa),
                    "token_in": voce.token_in,
                    "token_out": voce.token_out,
                    "costo_usd": voce.costo_usd,
                    "controllo": voce.controllo,
                    "categorie": voce.categorie,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            "utf-8",
        )
    return 0


def utente_attivo(db: Session, nome_utente: str) -> Utente:
    utente = db.scalar(select(Utente).where(Utente.nome_utente == nome_utente))
    if utente is None or not utente.attivo:
        raise CommandError(f"{nome_utente}: utente inesistente o non attivo.")
    return utente


def indice_per(percorsi: list[str], indice: str | None) -> Path:
    """L'indice dello studio: quello indicato, oppure indice.csv nella
    cartella degli atti o in quella che la contiene."""
    if indice:
        return Path(indice)
    for percorso in map(Path, percorsi):
        cartella = percorso if percorso.is_dir() else percorso.parent
        for candidato in (cartella, cartella.parent):
            if (candidato / "indice.csv").is_file():
                return candidato / "indice.csv"
    raise CommandError("Manca l'indice dello studio: indicalo con --indice.")


def riga_dell_atto(numero, data, autore, tipo) -> str:
    giorno_atto = data.isoformat() if data else "senza data"
    return f"{numero:02d}  {giorno_atto}  {autore or '?':<6} {tipo or '?'}"


def carica_l_archivio(db: Session, settings, args) -> int:
    utente = utente_attivo(db, args.da)
    if utente.ruolo != "avvocato":
        raise ArchivioRifiutato("L'archivio lo carica un avvocato.")
    indice = indice_per(args.percorsi, args.indice)
    persone = leggi_indice(indice)
    da = indice.as_posix()  # lo stesso percorso su ogni sistema
    print(f"Archivio, caricato da {utente.nome}; le persone da {da}:")
    autori = {u.id: u.nome_utente for u in db.scalars(select(Utente))}
    rifiutati = 0
    for percorso in file_da(args.percorsi):
        if percorso.suffix.lower() != ".pdf":
            continue
        elenco = persone.get(percorso.name) or persone.get(percorso.stem)
        try:
            atto = carica_atto(db, settings, utente, percorso, elenco)
        except (ArchivioRifiutato, motore.DocumentoNonLeggibile) as exc:
            db.rollback()
            print(f"{percorso.name}: {exc}")
            rifiutati += 1
            continue
        print(
            riga_dell_atto(
                atto.id, atto.data, autori.get(atto.autore_id), atto.tipo
            )
        )
    print(f"Atti nell'archivio: {len(atti_dell_archivio(db))}.")
    return 1 if rifiutati else 0


def stampa_archivio(db: Session, args) -> None:
    if not puo_leggere(utente_attivo(db, args.da)):
        raise ArchivioRifiutato("La segreteria non consulta l'archivio.")
    autori = {u.id: u.nome_utente for u in db.scalars(select(Utente))}
    atti = atti_dell_archivio(db)
    print(f"Atti nell'archivio: {len(atti)}.")
    for a in atti:
        print(riga_dell_atto(a.id, a.data, autori.get(a.autore_id), a.tipo))


def cerca_dalla_riga(db: Session, args) -> None:
    trovati = cerca_nell_archivio(
        db,
        utente_attivo(db, args.da),
        args.parole,
        args.tipo,
        args.autore,
        args.dal,
        args.al,
    )
    totale = db.scalar(select(func.count()).select_from(AttoArchivio))
    print(f"Atti con le parole cercate: {len(trovati)} su {totale}.")
    for t in trovati:
        a = t.atto
        print(riga_dell_atto(a.numero, a.data, a.autore, a.tipo))
        dove = " · ".join(
            f"pagina {n}: {', '.join(comuni)}"
            for n, comuni in t.pagine.items()
        )
        print("\n".join(a_capo(dove, "    ", "    ")))
    print("La ricerca è avvenuta nello studio: non è partito niente.")


# [libro:diagnosi]
def diagnosi(settings, engine) -> int:
    """Le informazioni utili per chiedere aiuto, senza segreti."""
    print(f"APP_ENV          {settings.app_env}")
    print(f"DATABASE_URL     {indirizzo_mascherato(settings.database_url)}")
    print(f"APP_ORIGIN       {settings.app_origin}")
    print(f"ALLOWED_HOSTS    {', '.join(settings.allowed_hosts)}")
    print(
        f"SECRET_KEY       {len(settings.secret_key)} caratteri (non mostrata)"
    )
    chiave = chiave_presente()
    stato = f"in {chiave} (non mostrata)" if chiave else "assente"
    print(f"Chiave modello   {stato}")
    nome = f" ({settings.modello_nome})" if settings.modello_nome else ""
    print(f"Modello          {settings.modello}{nome}")
    try:
        with engine.connect() as conn:
            versione = versione_attuale(conn)
    except Exception as exc:  # qui vogliamo vedere qualunque guasto
        print(f"Database         non raggiungibile: {type(exc).__name__}")
        return 1
    print(f"Schema           versione {versione}, attesa {ultima()}")
    if versione == ultima():
        with make_session_factory(engine)() as db:
            for ruolo in RUOLI:
                quanti = db.scalar(
                    select(func.count())
                    .select_from(Utente)
                    .where(Utente.ruolo == ruolo, Utente.attivo.is_(True))
                )
                print(f"Utenti attivi    {ruolo}: {quanti}")
            for nome, tabella in (
                ("Fascicoli", Fascicolo),
                ("Documenti", Documento),
                ("Persone", PersonaFascicolo),
                ("Schede", Scheda),
                ("Scadenze", Scadenza),
                ("Verifiche", Verifica),
                ("Risposte", RispostaFascicolo),
                ("Archivio", AttoArchivio),
                ("Eventi", Evento),
                ("Voci uso AI", UsoAI),
            ):
                quanti = db.scalar(select(func.count()).select_from(tabella))
                print(f"{nome:<16} {quanti}")
    print(f"Certificatori    {stato_elenco(settings)}")
    return 0 if versione == ultima() else 1


# [/libro:diagnosi]


if __name__ == "__main__":
    sys.exit(main())
