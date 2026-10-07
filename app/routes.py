"""I percorsi di Minuta.

Ogni percorso che scrive segue lo stesso ordine: chi sei (sessione), che
cosa puoi fare (ruolo), se il modulo è nostro (CSRF), su quale fascicolo
(visibilità), se i dati rispettano le regole, e solo alla fine la
scrittura, con la sua riga nel registro delle attività, nella stessa
transazione.
"""

from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from . import __version__
from .db import (
    Assegnazione,
    Documento,
    Evento,
    Fascicolo,
    SessioneAccesso,
    TentativoFallito,
    Utente,
    adesso,
)
from .documenti import (
    MASSIMO_DOCUMENTO,
    DocumentoRifiutato,
    carica,
    lettura_di,
    originale,
)
from .migrations import ultima, versione_attuale
from .rules import (
    APRONO,
    ValidationErrors,
    azioni_disponibili,
    campi_fascicolo,
    leggi_versione,
    passaggio_ammesso,
    passaggio_previsto,
)
from .security import (
    COOKIE_SESSIONE,
    HASH_FITTIZIO,
    impronta,
    nuovo_gettone,
    verifica_passphrase,
)
from .web import (
    apri_db,
    controlla_modulo,
    fascicoli_visibili,
    fascicolo_visibile,
    ip_client,
    opzioni_cookie_sessione,
    pagina,
    registra_evento,
    richiedi_ruolo,
    richiedi_utente,
    settings_of,
    utente_corrente,
)

router = APIRouter()

FINESTRA = timedelta(minutes=15)
MASSIMO_PER_NOME = 10
MASSIMO_PER_IP = 50
SUPERATO = (
    "Qualcuno ha modificato il fascicolo dopo che l'hai aperto: ricarica."
)


def vai_a(indirizzo: str) -> RedirectResponse:
    """Dopo un salvataggio il browser apre la pagina con una nuova GET."""
    return RedirectResponse(indirizzo, status_code=303)


def fallimenti_dal(db, colonna, valore, dal) -> int:
    query = select(func.count()).select_from(TentativoFallito)
    return db.scalar(
        query.where(colonna == valore, TentativoFallito.creato_il > dal)
    )


def attivi(db, ruolo: str) -> list[Utente]:
    query = (
        select(Utente)
        .where(Utente.ruolo == ruolo, Utente.attivo.is_(True))
        .order_by(Utente.nome)
    )
    return list(db.scalars(query))


def nomi(db) -> dict[int, str]:
    return {u.id: u.nome for u in db.scalars(select(Utente))}


# ----------------------------------------------------------------------
# Accesso e uscita
# ----------------------------------------------------------------------


@router.get("/", include_in_schema=False)
def inizio():
    return vai_a("/fascicoli")


@router.get("/accesso", response_class=HTMLResponse)
def pagina_accesso(request: Request):
    return pagina(request, "accesso.html", {})


@router.post("/accesso")
def accesso(
    request: Request,
    nome_utente: str = Form(""),
    passphrase: str = Form(""),
    csrf_token: str = Form(""),
):
    controlla_modulo(request, csrf_token)
    settings = settings_of(request)
    nome = nome_utente.strip().lower()[:40]
    ip = ip_client(request)
    dal = adesso() - FINESTRA
    with apri_db(request) as db:
        per_nome = fallimenti_dal(db, TentativoFallito.nome_utente, nome, dal)
        per_ip = fallimenti_dal(db, TentativoFallito.ip, ip, dal)
        if per_nome >= MASSIMO_PER_NOME or per_ip >= MASSIMO_PER_IP:
            errore = "Troppi tentativi. Riprova tra 15 minuti."
            return pagina(request, "accesso.html", {"errore": errore}, 429)

        utente = db.scalar(select(Utente).where(Utente.nome_utente == nome))
        salvato = utente.hash_passphrase if utente else HASH_FITTIZIO
        giusta = verifica_passphrase(salvato, passphrase)
        if utente is None or not giusta or not utente.attivo:
            db.add(TentativoFallito(nome_utente=nome, ip=ip))
            ieri = adesso() - timedelta(days=1)
            db.execute(  # i tentativi vecchi non servono più
                delete(TentativoFallito).where(
                    TentativoFallito.creato_il < ieri
                )
            )
            db.commit()
            errore = "Nome utente o passphrase non validi."
            return pagina(request, "accesso.html", {"errore": errore}, 401)

        precedente = request.cookies.get(COOKIE_SESSIONE)
        if precedente:  # la sessione vecchia non sopravvive al nuovo accesso
            db.execute(
                delete(SessioneAccesso).where(
                    SessioneAccesso.impronta == impronta(precedente)
                )
            )
        gettone = nuovo_gettone()
        ore = timedelta(hours=settings.session_hours)
        db.add(
            SessioneAccesso(
                impronta=impronta(gettone),  # salviamo solo l'impronta
                utente_id=utente.id,
                scade_il=adesso() + ore,
            )
        )
        registra_evento(db, utente, None, "accesso")
        db.commit()
    risposta = vai_a("/fascicoli")
    risposta.set_cookie(
        COOKIE_SESSIONE, gettone, **opzioni_cookie_sessione(settings)
    )
    return risposta


@router.post("/uscita")
def uscita(request: Request, csrf_token: str = Form("")):
    controlla_modulo(request, csrf_token)
    gettone = request.cookies.get(COOKIE_SESSIONE)
    with apri_db(request) as db:
        utente = utente_corrente(request, db)
        if gettone:
            db.execute(
                delete(SessioneAccesso).where(
                    SessioneAccesso.impronta == impronta(gettone)
                )
            )
        if utente is not None:
            registra_evento(db, utente, None, "uscita")
        db.commit()
    risposta = vai_a("/accesso")
    risposta.delete_cookie(COOKIE_SESSIONE, path="/")
    return risposta


# ----------------------------------------------------------------------
# Fascicoli
# ----------------------------------------------------------------------


@router.get("/fascicoli", response_class=HTMLResponse)
def elenco(request: Request):
    with apri_db(request) as db:
        utente = richiedi_utente(request, db)
        query = fascicoli_visibili(utente).order_by(Fascicolo.codice)
        fascicoli = list(db.scalars(query))
        persone = nomi(db)
    contesto = {"utente": utente, "fascicoli": fascicoli, "nomi": persone}
    return pagina(request, "fascicoli.html", contesto)


@router.get("/fascicoli/nuovo", response_class=HTMLResponse)
def pagina_nuovo(request: Request):
    with apri_db(request) as db:
        utente = richiedi_utente(request, db)
        richiedi_ruolo(utente, *APRONO)
        contesto = {
            "utente": utente,
            "valori": {},
            "errori": {},
            "avvocati": attivi(db, "avvocato"),
            "praticanti": attivi(db, "praticante"),
        }
    return pagina(request, "nuovo.html", contesto)


# [libro:apri-fascicolo]
@router.post("/fascicoli/nuovo")
def apri_fascicolo(
    request: Request,
    codice: str = Form(""),
    cliente: str = Form(""),
    materia: str = Form(""),
    oggetto: str = Form(""),
    avvocato_id: str = Form(""),
    praticante_id: str = Form(""),
    csrf_token: str = Form(""),
):
    grezzi = {
        "codice": codice,
        "cliente": cliente,
        "materia": materia,
        "oggetto": oggetto,
        "avvocato_id": avvocato_id,
        "praticante_id": praticante_id,
    }
    with apri_db(request) as db:
        utente = richiedi_utente(request, db)  # chi sei
        richiedi_ruolo(utente, *APRONO)  # che cosa puoi fare
        controlla_modulo(request, csrf_token)  # il modulo è nostro
        avvocati = attivi(db, "avvocato")
        praticanti = attivi(db, "praticante")
        try:
            campi = campi_fascicolo(
                grezzi, {a.id for a in avvocati}, {p.id for p in praticanti}
            )
        except ValidationErrors as exc:
            contesto = {
                "utente": utente,
                "valori": grezzi,
                "errori": exc.errori,
                "avvocati": avvocati,
                "praticanti": praticanti,
            }
            return pagina(request, "nuovo.html", contesto, 422)
        if db.scalar(select(Fascicolo).where(Fascicolo.codice == codice)):
            raise HTTPException(
                409, "Esiste già un fascicolo con quel codice."
            )
        praticante = campi.pop("praticante_id")
        # Chi apre viene dalla sessione, mai da un campo del modulo.
        fascicolo = Fascicolo(**campi, creato_da_id=utente.id)
        db.add(fascicolo)
        db.flush()  # ora il database ha assegnato il numero
        persone = {utente.id, fascicolo.avvocato_id} | (
            {praticante} if praticante else set()
        )
        for persona in sorted(persone):
            db.add(Assegnazione(fascicolo_id=fascicolo.id, utente_id=persona))
        registra_evento(
            db, utente, fascicolo, "apertura", persone=sorted(persone)
        )
        db.commit()
        numero = fascicolo.id
    return vai_a(f"/fascicoli/{numero}")


# [/libro:apri-fascicolo]


@router.get("/fascicoli/{fascicolo_id}", response_class=HTMLResponse)
def scheda_fascicolo(request: Request, fascicolo_id: int):
    with apri_db(request) as db:
        utente = richiedi_utente(request, db)
        fascicolo = fascicolo_visibile(db, fascicolo_id, utente)
        query = (
            select(Evento)
            .where(Evento.fascicolo_id == fascicolo.id)
            .order_by(Evento.creato_il, Evento.id)
        )
        eventi = list(db.scalars(query))
        assegnati = list(
            db.scalars(
                select(Assegnazione.utente_id).where(
                    Assegnazione.fascicolo_id == fascicolo.id
                )
            )
        )
        persone = nomi(db)
        documenti = list(
            db.scalars(
                select(Documento)
                .where(Documento.fascicolo_id == fascicolo.id)
                .order_by(Documento.id)
            )
        )
    contesto = {
        "utente": utente,
        "fascicolo": fascicolo,
        "nomi": persone,
        "documenti": documenti,
        "assegnati": [persone[i] for i in assegnati],
        "azioni": azioni_disponibili(fascicolo.stato, utente.ruolo),
        "storia": [(e, json.loads(e.dettaglio or "{}")) for e in eventi],
    }
    return pagina(request, "fascicolo.html", contesto)


# [libro:cambia-stato]
@router.post("/fascicoli/{fascicolo_id}/stato")
def cambia_stato(
    request: Request,
    fascicolo_id: int,
    stato: str = Form(""),
    versione: str = Form(""),
    csrf_token: str = Form(""),
):
    with apri_db(request) as db:
        utente = richiedi_utente(request, db)  # chi sei
        controlla_modulo(request, csrf_token)  # il modulo è nostro
        fascicolo = fascicolo_visibile(db, fascicolo_id, utente)  # quale
        attesa = leggi_versione(versione)
        if attesa is None:
            raise HTTPException(422, "Versione del modulo non valida.")
        if attesa != fascicolo.versione:
            raise HTTPException(409, SUPERATO)
        if not passaggio_previsto(fascicolo.stato, stato):
            raise HTTPException(422, "Passaggio di stato non previsto.")
        if not passaggio_ammesso(fascicolo.stato, stato, utente.ruolo):
            raise HTTPException(403, "Il tuo ruolo non consente il passaggio.")
        prima = fascicolo.stato
        # Aggiorna solo se la versione è ancora quella letta:
        # controllo e scrittura stanno nella stessa istruzione SQL.
        esito = db.execute(
            update(Fascicolo)
            .where(Fascicolo.id == fascicolo.id, Fascicolo.versione == attesa)
            .values(
                stato=stato,
                versione=Fascicolo.versione + 1,
                aggiornato_il=adesso(),
            )
        )
        if esito.rowcount != 1:
            raise HTTPException(409, SUPERATO)
        registra_evento(
            db, utente, fascicolo, "stato", prima=prima, dopo=stato
        )
        db.commit()  # la modifica e la sua riga, insieme o per niente
    return vai_a(f"/fascicoli/{fascicolo_id}")


# [/libro:cambia-stato]


# ----------------------------------------------------------------------
# Documenti del fascicolo (lezione 16)
# ----------------------------------------------------------------------


# [libro:rotta-documenti]
@router.post("/fascicoli/{fascicolo_id}/documenti")
def carica_documento(
    request: Request,
    fascicolo_id: int,
    file: UploadFile = File(...),
    csrf_token: str = Form(""),
):
    with apri_db(request) as db:
        utente = richiedi_utente(request, db)  # chi sei
        controlla_modulo(request, csrf_token)  # il modulo è nostro
        fascicolo = fascicolo_visibile(db, fascicolo_id, utente)  # quale
        dati = file.file.read(MASSIMO_DOCUMENTO + 1)
        try:
            documento, _lettura = carica(
                db,
                settings_of(request),
                utente,
                fascicolo,
                file.filename or "",
                dati,
            )
        except DocumentoRifiutato as exc:
            raise HTTPException(422, str(exc)) from None
        numero = documento.id
    return vai_a(f"/fascicoli/{fascicolo_id}/documenti/{numero}")


# [/libro:rotta-documenti]


def documento_visibile(db, fascicolo_id: int, documento_id: int, utente):
    """Il documento, se sta in un fascicolo a cui l'utente lavora."""
    fascicolo = fascicolo_visibile(db, fascicolo_id, utente)
    documento = db.get(Documento, documento_id)
    if documento is None or documento.fascicolo_id != fascicolo.id:
        raise HTTPException(404, "Documento non trovato.")
    return fascicolo, documento


@router.get(
    "/fascicoli/{fascicolo_id}/documenti/{documento_id}",
    response_class=HTMLResponse,
)
def scheda_documento(request: Request, fascicolo_id: int, documento_id: int):
    with apri_db(request) as db:
        utente = richiedi_utente(request, db)
        fascicolo, documento = documento_visibile(
            db, fascicolo_id, documento_id, utente
        )
        persone = nomi(db)
    contesto = {
        "utente": utente,
        "fascicolo": fascicolo,
        "documento": documento,
        "lettura": lettura_di(documento),
        "nomi": persone,
    }
    return pagina(request, "documento.html", contesto)


@router.get("/fascicoli/{fascicolo_id}/documenti/{documento_id}/originale")
def scarica_originale(request: Request, fascicolo_id: int, documento_id: int):
    """L'originale, com'è arrivato: si scarica, non si apre nel browser."""
    with apri_db(request) as db:
        utente = richiedi_utente(request, db)
        _fascicolo, documento = documento_visibile(
            db, fascicolo_id, documento_id, utente
        )
    percorso = originale(settings_of(request), documento)
    if not percorso.is_file():
        raise HTTPException(404, "L'originale non si trova nella cartella.")
    disposizione = f"attachment; filename*=UTF-8''{quote(documento.nome)}"
    return Response(
        percorso.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": disposizione},
    )


# ----------------------------------------------------------------------
# Controlli di salute
# ----------------------------------------------------------------------


@router.get("/salute")
def salute():
    """Il processo risponde. Non dice niente del database."""
    return {"stato": "ok", "versione": __version__}


@router.get("/pronto")
def pronto(request: Request):
    """Il processo risponde e il database ha lo schema atteso."""
    try:
        with request.app.state.engine.connect() as conn:
            versione = versione_attuale(conn)
    except SQLAlchemyError:
        corpo = {"stato": "non disponibile", "dettaglio": "database assente"}
        return JSONResponse(corpo, status_code=503)
    if versione != ultima():
        corpo = {
            "stato": "non disponibile",
            "schema": versione,
            "atteso": ultima(),
        }
        return JSONResponse(corpo, status_code=503)
    return {"stato": "pronto", "schema": versione}
