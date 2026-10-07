"""Preparazione delle prove dell'applicazione.

Ogni prova riceve un database SQLite nuovo e vuoto, in una cartella
temporanea, e le persone di Studio Meridiana.
"""

from __future__ import annotations

import pytest
from aiuti import PASSPHRASE, PERSONE, accedi
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.manage import crea_utente
from app.migrations import migra

SEGRETO = "segreto-delle-prove-" + "x" * 40


@pytest.fixture
def impostazioni(tmp_path):
    indirizzo = f"sqlite:///{(tmp_path / 'studio-prova.db').as_posix()}"
    return Settings(
        app_env="test",
        secret_key=SEGRETO,
        database_url=indirizzo,
        app_origin="http://testserver",
        allowed_hosts=("testserver",),
    ).validate()


@pytest.fixture
def app_vuota(impostazioni):
    """L'applicazione su un database vuoto, senza schema né utenti."""
    applicazione = create_app(impostazioni)
    yield applicazione
    applicazione.state.engine.dispose()


@pytest.fixture
def app(app_vuota):
    """L'applicazione con lo schema e le persone di Studio Meridiana."""
    migra(app_vuota.state.engine)
    with app_vuota.state.session_factory() as db:
        for nome_utente, (ruolo, nome) in PERSONE.items():
            crea_utente(db, nome_utente, ruolo, nome, PASSPHRASE[nome_utente])
    return app_vuota


@pytest.fixture
def browser(app):
    """Un browser di prova, già entrato come la persona indicata."""
    aperti = []

    def apri(nome_utente: str | None = None) -> TestClient:
        client = TestClient(app)
        aperti.append(client)
        if nome_utente is not None:
            risposta = accedi(client, nome_utente)
            assert risposta.status_code == 303, risposta.text
        return client

    yield apri
    for client in aperti:
        client.close()
