"""Assembla l'applicazione: configurazione, database, protezioni, percorsi."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings, load_settings
from .db import make_engine, make_session_factory
from .documenti import MASSIMO_DOCUMENTO
from .invio import modello_da
from .routes import router
from .web import LoginRequired, pagina_errore

QUI = Path(__file__).resolve().parent
MASSIMO_CORPO = 16_384  # i moduli sono piccoli
# Il caricamento di un documento: il file e il modulo che lo porta.
MASSIMO_CARICAMENTO = MASSIMO_DOCUMENTO + 65_536
CARICAMENTO = re.compile(r"/fascicoli/\d+/documenti")

# [libro:intestazioni]
INTESTAZIONI_SICUREZZA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; img-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
}
# [/libro:intestazioni]

MESSAGGI = {
    404: "Pagina non trovata.",
    405: "Operazione non consentita su questo indirizzo.",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)

    app = FastAPI(
        title="Minuta", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.templates = Jinja2Templates(directory=str(QUI / "templates"))
    # Il modello indicato in MINUTA_MODELLO; senza, quello finto (lezione 17).
    app.state.modello = modello_da(settings)
    app.mount("/static", StaticFiles(directory=str(QUI / "static")), "static")
    app.include_router(router)

    @app.middleware("http")
    async def limiti_e_intestazioni(request: Request, call_next):
        if request.method == "POST":
            lunghezza = request.headers.get("content-length", "")
            if not (lunghezza.isascii() and lunghezza.isdigit()):
                return PlainTextResponse(
                    "Lunghezza assente o non valida.", 411
                )
            limite = (
                MASSIMO_CARICAMENTO
                if CARICAMENTO.fullmatch(request.url.path)
                else MASSIMO_CORPO
            )
            if int(lunghezza) > limite:
                return PlainTextResponse("Richiesta troppo grande.", 413)
        risposta = await call_next(request)
        for nome, valore in INTESTAZIONI_SICUREZZA.items():
            risposta.headers.setdefault(nome, valore)
        return risposta

    # Aggiunto per ultimo, quindi è il primo controllo che la richiesta
    # incontra: un nome di host non previsto viene respinto subito.
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts)
    )

    @app.exception_handler(LoginRequired)
    async def accesso_richiesto(request: Request, _exc: LoginRequired):
        if request.method in ("GET", "HEAD"):
            return RedirectResponse("/accesso", status_code=303)
        messaggio = "Sessione assente o scaduta: accedi di nuovo."
        return pagina_errore(request, 401, messaggio)

    @app.exception_handler(StarletteHTTPException)
    async def errore_http(request: Request, exc: StarletteHTTPException):
        dettaglio = exc.detail
        if not isinstance(dettaglio, str) or dettaglio in (
            "Not Found",
            "Method Not Allowed",
        ):
            dettaglio = MESSAGGI.get(exc.status_code, "Richiesta non valida.")
        return pagina_errore(request, exc.status_code, dettaglio)

    @app.exception_handler(RequestValidationError)
    async def richiesta_non_valida(request: Request, _exc):
        return pagina_errore(request, 422, "Dati della richiesta non validi.")

    return app
