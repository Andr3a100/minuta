import json
from pathlib import Path

import pytest

from minuta import archive, citations, profile

from percorsi import RADICE


@pytest.fixture(scope="session")
def config():
    return archive.carica_config(RADICE / "config/studio.json")


@pytest.fixture(scope="session")
def db(config):
    connessione = archive.apri(Path(":memory:"))
    archive.importa(RADICE / "archivio/pdf", connessione, config)
    return connessione


@pytest.fixture(scope="session")
def atti(config):
    return {p.stem: archive.leggi_atto(p, config["avvocati"])
            for p in sorted((RADICE / "archivio/pdf").glob("*.pdf"))}


@pytest.fixture(scope="session")
def oracolo():
    dati = json.loads((RADICE / "archivio/entita.json").read_text("utf-8"))
    dati.pop("_nota")
    return dati


@pytest.fixture(scope="session")
def profilo(db, config):
    return profile.calcola(db, profile.noti_dello_studio(config))


@pytest.fixture(scope="session")
def massimario():
    return citations.Massimario(RADICE / "config/massimario.json")


@pytest.fixture
def fascicolo():
    return json.loads((RADICE / "tests/fascicolo-prova.json").read_text("utf-8"))
