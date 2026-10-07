"""Le domande al modello sui documenti del fascicolo (lezione 17).

Ogni domanda segue lo stesso ordine. Chi chiama ha già controllato chi
chiede, su quale fascicolo e quale documento. Qui il testo da mandare, chi
chiede, la domanda e il documento, passa dalla preparazione del motore
(minuta/invio.py), con l'elenco delle persone del fascicolo e i segnaposto
già usati. Se la preparazione trova fughe o nomi fuori elenco, la domanda
non parte; il testo nascosto del documento non la ferma, ma si mostra
prima. Se parte, il registro dell'uso dell'AI ne scrive la voce, la tabella
dei segnaposto si aggiorna, e la risposta torna con i nomi veri, ricomposti
nello studio, tutto nella stessa transazione.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.invio import (
    SISTEMA,
    Preparato,
    prepara,
    ricomponi,
    segnaposto_sconosciuti,
)
from minuta.model import (
    Modello,
    ModelloAnthropic,
    ModelloCompatibileOpenAI,
    ModelloFinto,
    carica_env,
)

from .db import (
    Assegnazione,
    Documento,
    Fascicolo,
    PersonaFascicolo,
    Segnaposto,
    UsoAI,
    Utente,
)
from .documenti import lettura_di
from .registro import chiedi
from .web import registra_evento


def modello_da(settings) -> Modello:
    """Il modello della configurazione. Solo per un fornitore vero si legge
    la sua chiave dal file .env, e non si mostra mai."""
    if settings.modello == "finto":
        return ModelloFinto()
    carica_env(Path(".env"))
    if settings.modello == "openai":
        return ModelloCompatibileOpenAI(settings.modello_nome)
    return ModelloAnthropic(settings.modello_nome)


class PersonaRifiutata(Exception):
    """La persona non entra nell'elenco: il messaggio dice perché."""


def aggiungi_persona(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    nome: str,
    ruolo: str,
    soggetto: bool = False,
) -> PersonaFascicolo:
    """Aggiunge una persona all'elenco, con la sua riga nel registro delle
    attività. Chi chiama ha già controllato chi aggiunge."""
    nome, ruolo = " ".join(nome.split()), " ".join(ruolo.split())
    if not 2 <= len(nome) <= 120:
        raise PersonaRifiutata("Il nome va da 2 a 120 caratteri.")
    if not 1 <= len(ruolo) <= 60:
        raise PersonaRifiutata("Il ruolo va da 1 a 60 caratteri.")
    gia = db.scalar(
        select(PersonaFascicolo).where(
            PersonaFascicolo.fascicolo_id == fascicolo.id,
            PersonaFascicolo.nome == nome,
        )
    )
    if gia is not None:
        raise PersonaRifiutata(f"{nome} è già nell'elenco.")
    persona = PersonaFascicolo(
        fascicolo_id=fascicolo.id,
        nome=nome,
        tipo="SOGGETTO" if soggetto else "PERSONA",
        ruolo=ruolo,
        aggiunta_da_id=utente.id,
    )
    db.add(persona)
    db.flush()
    registra_evento(db, utente, fascicolo, "persona", nome=nome, ruolo=ruolo)
    db.commit()
    return persona


SOCIETA = re.compile(r"S\.(?:r\.l|p\.A|n\.c|a\.s)\.", re.I)


def cliente_in_elenco(db: Session, fascicolo: Fascicolo) -> None:
    """Il cliente è la prima persona dell'elenco, dal giorno dell'apertura."""
    societa = SOCIETA.search(fascicolo.cliente)
    db.add(
        PersonaFascicolo(
            fascicolo_id=fascicolo.id,
            nome=fascicolo.cliente,
            tipo="SOGGETTO" if societa else "PERSONA",
            ruolo="cliente",
        )
    )


class InvioBloccato(Exception):
    """Il testo da mandare contiene ancora qualcosa di riconoscibile."""

    def __init__(self, preparato: Preparato):
        super().__init__("Invio bloccato: il testo non è pulito.")
        self.preparato = preparato


@dataclass
class Esito:
    risposta: str  # ricomposta nello studio, con i nomi veri
    arrivata: str  # com'è arrivata dal fornitore, con i segnaposto
    voce: UsoAI
    sconosciuti: list[str]  # segnaposto che la tabella non conosce
    preparato: Preparato


# [libro:noti]
def noti_del_fascicolo(db: Session, fascicolo: Fascicolo) -> dict[str, str]:
    """I nomi da nascondere: l'elenco del fascicolo, più le persone dello
    studio che ci lavorano, quando hanno nome e cognome."""
    noti = {
        p.nome: p.tipo
        for p in db.scalars(
            select(PersonaFascicolo).where(
                PersonaFascicolo.fascicolo_id == fascicolo.id
            )
        )
    }
    assegnati = db.scalars(
        select(Utente)
        .join(Assegnazione, Assegnazione.utente_id == Utente.id)
        .where(Assegnazione.fascicolo_id == fascicolo.id)
    )
    for persona in assegnati:
        if len(persona.nome.split()) >= 2:
            noti.setdefault(persona.nome, "PERSONA")
    return noti


# [/libro:noti]


def tabella_del_fascicolo(db: Session, fascicolo: Fascicolo) -> dict:
    righe = db.scalars(
        select(Segnaposto).where(Segnaposto.fascicolo_id == fascicolo.id)
    )
    return {r.segno: r.valore for r in righe}


def chi_chiede(utente: Utente, fascicolo: Fascicolo) -> str:
    """Chi fa la domanda, e per chi: dai segnaposto il modello non lo
    ricava. Il nome c'è se ha anche il cognome, cioè se diventa un
    segnaposto."""
    nome = f"{utente.nome}, " if len(utente.nome.split()) >= 2 else ""
    return f"{nome}{utente.ruolo} dello studio che assiste {fascicolo.cliente}"


def testo_da_mandare(documento: Documento, domanda: str, chi: str) -> str:
    pagine = lettura_di(documento)["pagine"]
    testo = "\n\n".join(p["testo"] for p in pagine if p["testo"])
    inizio = ""
    if domanda.strip():
        inizio = f"CHI CHIEDE: {chi}\nDOMANDA: {domanda.strip()}\n\n"
    return f"{inizio}DOCUMENTO: {documento.nome}\n{testo}"


def testo_nascosto(documento: Documento) -> list[str]:
    """Il testo nascosto trovato alla lettura (lezione 16): il modello lo
    leggerebbe come il resto, e l'avvocato lo vede prima (lezione 12)."""
    return [
        f"pagina {n['pagina']}, {n['motivo']}: «{n['testo']}»"
        for n in lettura_di(documento)["nascosti"]
    ]


def prepara_domanda(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    documento: Documento,
    domanda: str,
) -> tuple[Preparato, int]:
    """Il testo che partirebbe, con l'esito dei controlli, e quanti nomi
    conosceva Minuta."""
    noti = noti_del_fascicolo(db, fascicolo)
    preparato = prepara(
        testo_da_mandare(documento, domanda, chi_chiede(utente, fascicolo)),
        noti,
        tabella_del_fascicolo(db, fascicolo),
    )
    preparato.nascosto = testo_nascosto(documento)
    return preparato, len(noti)


def categorie(fascicolo: Fascicolo, preparato: Preparato) -> str:
    """Le categorie di dati della voce del registro (lezione 8)."""
    voci = ["dati personali pseudonimizzati"]
    if fascicolo.materia == "penale":
        voci.append("dati relativi a reati")
    if preparato.salute:
        voci.append("dati sulla salute")
    return "; ".join(voci)


# [libro:domanda]
def domanda_sul_documento(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    documento: Documento,
    domanda: str,
    modello: Modello,
) -> Esito:
    preparato, persone = prepara_domanda(
        db, utente, fascicolo, documento, domanda
    )
    if preparato.bloccato:
        raise InvioBloccato(preparato)
    risposta, voce = chiedi(
        db,
        utente,
        fascicolo,
        modello,
        SISTEMA,
        preparato.testo,
        scopo="domanda su un documento del fascicolo",
        categorie=categorie(fascicolo, preparato),
        controllo=preparato.controllo(persone),
    )
    usati = tabella_del_fascicolo(db, fascicolo)
    for segno, valore in preparato.tabella.items():
        if segno not in usati:
            db.add(
                Segnaposto(
                    fascicolo_id=fascicolo.id, segno=segno, valore=valore
                )
            )
    db.commit()  # la voce del registro e i segnaposto, insieme
    return Esito(
        risposta=ricomponi(risposta.testo, preparato.tabella),
        arrivata=risposta.testo,
        voce=voce,
        sconosciuti=segnaposto_sconosciuti(risposta.testo, preparato.tabella),
        preparato=preparato,
    )


# [/libro:domanda]
