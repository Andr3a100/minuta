"""L'insieme di addestramento, nell'applicazione (lezione 28)."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest
from sqlalchemy import select
from test_app_stile import archivio, utente  # noqa: F401

from app import addestramento as app_addestramento
from app import manage
from app.addestramento import AddestramentoRifiutato, prepara_insieme
from app.db import AttoArchivio, Evento


def test_l_insieme_resta_nello_studio_senza_nomi_ne_fatti(
    app, archivio, impostazioni
):
    with app.state.session_factory() as db:
        insieme = prepara_insieme(db, impostazioni, utente(db, "sarti"))
        evento = db.scalar(
            select(Evento).where(Evento.azione == "addestramento")
        )
        persone = {
            n
            for a in db.scalars(select(AttoArchivio))
            for n in json.loads(a.persone)
        }
    righe = [
        json.loads(r) for r in insieme.percorso.read_text("utf-8").splitlines()
    ]
    assert insieme.percorso.parent.parent.as_posix() == impostazioni.data_dir
    assert [r["atto"] for r in righe] == [
        "archivio-01",
        "archivio-02",
        "archivio-05",
        "archivio-07",
        "archivio-10",
    ]  # gli atti di Elena Sarti
    tutto = "\n".join(r["testo"] for r in righe)
    assert not [n for n in persone | {"Elena Sarti"} if n in tutto]
    assert "[IMPORTO]" in tutto and "D.Lgs." in tutto
    assert insieme.tolti["[IMPORTO]"] > 0 and insieme.tolti["[DATA]"] > 0
    assert json.loads(evento.dettaglio) == {
        "atti": 5,
        "impronta": insieme.impronta,
    }  # nel registro l'impronta, mai il testo


def test_un_nome_rimasto_ferma_tutto(app, archivio, impostazioni):
    with app.state.session_factory() as db:
        sarti = utente(db, "sarti")
        atto = db.scalar(select(AttoArchivio).where(AttoArchivio.id == 7))
        pagine = json.loads(atto.pagine)
        atto.pagine = json.dumps([pagine[0] + "\nLo conferma Bruno Ferretti."])
        db.commit()
        with pytest.raises(AddestramentoRifiutato, match="archivio-07"):
            prepara_insieme(db, impostazioni, sarti)
    assert not list(Path(impostazioni.data_dir).glob("addestramento/*"))


def test_un_fatto_sfuggito_ferma_tutto(
    app, archivio, impostazioni, monkeypatch
):
    """La rete: se la generalizzazione lasciasse un fatto, non si scrive."""
    monkeypatch.setattr(app_addestramento, "senza_fatti", lambda testo: testo)
    with app.state.session_factory() as db:
        with pytest.raises(AddestramentoRifiutato, match="resta: data"):
            prepara_insieme(db, impostazioni, utente(db, "sarti"))


def test_chi_puo_e_quando(app, archivio, impostazioni):
    with app.state.session_factory() as db:
        with pytest.raises(AddestramentoRifiutato, match="di un avvocato"):
            prepara_insieme(db, impostazioni, utente(db, "irene"))
        with pytest.raises(AddestramentoRifiutato, match="almeno due"):
            prepara_insieme(db, impostazioni, utente(db, "righi"))


def test_il_comando(app, archivio, impostazioni, capsys):
    with app.state.session_factory() as db:
        manage.insieme_dalla_riga(db, impostazioni, Namespace(da="sarti"))
    righe = capsys.readouterr().out.splitlines()
    assert righe[0].startswith("L'insieme per lo stile di Elena Sarti: 5 atti")
    assert righe[2] == "Nomi rimasti: 0. Fatti rimasti: 0."
    assert righe[3].endswith(": resta nello studio, non parte niente.")
