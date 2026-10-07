"""Strumenti comuni alle prove dell'applicazione: persone, accesso, moduli."""

from __future__ import annotations

import re

from sqlalchemy import select

from app.db import Fascicolo
from app.manage import crea_prova

# Le persone di Studio Meridiana, con il loro ruolo in Minuta (lezione 5).
PERSONE = {
    "sarti": ("avvocato", "Elena Sarti"),
    "dini": ("avvocato", "Marco Dini"),
    "righi": ("avvocato", "Paola Righi"),
    "valli": ("avvocato", "Stefano Valli"),
    "irene": ("praticante", "Irene"),
    "rosa": ("segreteria", "Rosa"),
}
PASSPHRASE = {nome: f"passphrase di prova per {nome}" for nome in PERSONE}
GETTONE = re.compile(r'name="csrf_token" value="([^"]+)"')


def gettone_da(client, indirizzo: str = "/accesso") -> str:
    """Apre una pagina e restituisce il permesso di invio del modulo."""
    risposta = client.get(indirizzo)
    trovato = GETTONE.search(risposta.text)
    assert trovato, f"nessun csrf_token nella pagina {indirizzo}"
    return trovato.group(1)


def accedi(client, nome_utente: str, passphrase: str | None = None):
    dati = {
        "nome_utente": nome_utente,
        "passphrase": PASSPHRASE[nome_utente]
        if passphrase is None
        else passphrase,
        "csrf_token": gettone_da(client, "/accesso"),
    }
    return client.post("/accesso", data=dati, follow_redirects=False)


def carica_file(client, fascicolo, nome: str, dati: bytes):
    """Carica un documento dalla pagina del fascicolo, come dal browser."""
    gettone = gettone_da(client, "/fascicoli")
    return client.post(
        f"/fascicoli/{fascicolo.id}/documenti",
        data={"csrf_token": gettone},
        files={"file": (nome, dati, "application/octet-stream")},
        follow_redirects=False,
    )


def invia(client, indirizzo: str, dati: dict, pagina: str = "/fascicoli"):
    """Invia un modulo con un permesso di invio valido per la sessione."""
    carico = {"csrf_token": gettone_da(client, pagina), **dati}
    return client.post(indirizzo, data=carico, follow_redirects=False)


def con_fascicoli(app) -> dict[str, Fascicolo]:
    """Crea i tre fascicoli di prova e li restituisce per codice."""
    with app.state.session_factory() as db:
        crea_prova(db, production=False)
        return {f.codice: f for f in db.scalars(select(Fascicolo))}
