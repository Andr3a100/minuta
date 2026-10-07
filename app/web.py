"""I controlli che ogni percorso ripete: chi sei, che cosa puoi fare, su
quale fascicolo, se il modulo è autentico. Più la composizione delle pagine.
"""

from __future__ import annotations

import json
import secrets

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import (
    Assegnazione,
    Evento,
    Fascicolo,
    SessioneAccesso,
    Utente,
    adesso,
)
from .rules import ETICHETTE_MATERIE, ETICHETTE_RUOLI, ETICHETTE_STATI
from .security import (
    COOKIE_CSRF,
    COOKIE_SESSIONE,
    csrf_valido,
    gettone_csrf,
    impronta,
    legame_sessione,
)


class LoginRequired(Exception):
    """La richiesta arriva senza una sessione valida."""


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def apri_db(request: Request) -> Session:
    """Una sessione di lavoro con il database, da usare con with."""
    return request.app.state.session_factory()


def utente_corrente(request: Request, db: Session) -> Utente | None:
    """L'utente della sessione: cookie valido, non scaduto, utente attivo."""
    gettone = request.cookies.get(COOKIE_SESSIONE)
    if not gettone:
        return None
    riga = db.execute(
        select(SessioneAccesso, Utente)
        .join(Utente, SessioneAccesso.utente_id == Utente.id)
        .where(SessioneAccesso.impronta == impronta(gettone))
    ).first()
    if riga is None:
        return None
    sessione, utente = riga
    if sessione.scade_il <= adesso() or not utente.attivo:
        return None
    return utente


def richiedi_utente(request: Request, db: Session) -> Utente:
    utente = utente_corrente(request, db)
    if utente is None:
        raise LoginRequired()
    return utente


def richiedi_ruolo(utente: Utente, *ruoli: str) -> None:
    if utente.ruolo not in ruoli:
        raise HTTPException(403, "Il tuo ruolo non consente l'operazione.")


# [libro:visibili]
def fascicoli_visibili(utente: Utente):
    """La query di partenza: ciascuno vede solo i fascicoli a cui lavora."""
    assegnati = select(Assegnazione.fascicolo_id).where(
        Assegnazione.utente_id == utente.id
    )
    return select(Fascicolo).where(Fascicolo.id.in_(assegnati))


def fascicolo_visibile(db: Session, fascicolo_id: int, utente: Utente):
    """Conoscere il numero di un fascicolo non dà il diritto di aprirlo."""
    fascicolo = db.scalar(
        fascicoli_visibili(utente).where(Fascicolo.id == fascicolo_id)
    )
    if fascicolo is None:
        raise HTTPException(404, "Fascicolo non trovato.")
    return fascicolo


# [/libro:visibili]


def controlla_modulo(request: Request, gettone: str) -> None:
    """Accetta un modulo solo se è nato da una nostra pagina, da poco."""
    settings = settings_of(request)
    origine = request.headers.get("origin")
    if origine is not None and origine.rstrip("/") != settings.app_origin:
        raise HTTPException(403, "Origine della richiesta non ammessa.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Richiesta arrivata da un altro sito.")
    cookie = request.cookies.get(COOKIE_CSRF, "")
    legame = legame_sessione(request.cookies.get(COOKIE_SESSIONE))
    segreto = settings.secret_key
    if not cookie or not csrf_valido(segreto, cookie, legame, gettone):
        raise HTTPException(
            403, "Il modulo è scaduto o non è valido: ricarica la pagina."
        )


# [libro:evento]
def registra_evento(db: Session, utente, fascicolo, azione: str, **dettaglio):
    """Ogni scrittura lascia una riga nel registro delle attività.

    La riga entra nella stessa transazione della modifica: se la modifica
    non viene salvata, non resta neanche la riga, e viceversa.
    """
    db.add(
        Evento(
            utente_id=utente.id if utente else None,
            fascicolo_id=fascicolo.id if fascicolo else None,
            azione=azione,
            dettaglio=json.dumps(
                dettaglio, ensure_ascii=False, sort_keys=True
            ),
        )
    )


# [/libro:evento]


def pagina(request: Request, nome: str, contesto: dict, status_code=200):
    """Compone una pagina e le allega il permesso di invio dei moduli."""
    settings = settings_of(request)
    cookie = request.cookies.get(COOKIE_CSRF)
    nuovo = not cookie
    if nuovo:
        cookie = secrets.token_urlsafe(32)
    legame = legame_sessione(request.cookies.get(COOKIE_SESSIONE))
    valori = {
        "csrf_token": gettone_csrf(settings.secret_key, cookie, legame),
        "etichette_stati": ETICHETTE_STATI,
        "etichette_ruoli": ETICHETTE_RUOLI,
        "etichette_materie": ETICHETTE_MATERIE,
        "utente": None,
        **contesto,
    }
    modelli = request.app.state.templates
    risposta = modelli.TemplateResponse(
        request, nome, valori, status_code=status_code
    )
    if nuovo:
        risposta.set_cookie(
            COOKIE_CSRF,
            cookie,
            httponly=True,
            samesite="lax",
            secure=settings.production,
            path="/",
        )
    risposta.headers["Cache-Control"] = "no-store"
    return risposta


def pagina_errore(request: Request, status_code: int, messaggio: str):
    """Una pagina d'errore leggibile, senza dettagli interni."""
    modelli = request.app.state.templates
    risposta = modelli.TemplateResponse(
        request,
        "errore.html",
        {"status_code": status_code, "messaggio": messaggio},
        status_code=status_code,
    )
    risposta.headers["Cache-Control"] = "no-store"
    return risposta


def ip_client(request: Request) -> str:
    """L'indirizzo del client che ha fatto la richiesta."""
    return (request.client.host if request.client else "sconosciuto")[:64]


def opzioni_cookie_sessione(settings: Settings) -> dict:
    return {
        "httponly": True,  # lo script della pagina non può leggerlo (B6)
        "samesite": "lax",  # limita l'invio da altri siti
        "secure": settings.production,  # in produzione solo su HTTPS
        "max_age": settings.session_hours * 3600,
        "path": "/",
    }
