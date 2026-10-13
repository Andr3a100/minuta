"""Il glossario del fascicolo, nell'applicazione (lezione 29)."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest
from sqlalchemy import inspect, select
from test_app_bozze import ModelloCheRicorda, civile, utente  # noqa: F401

from app import manage
from app.db import Evento, Fascicolo, make_engine
from app.glossario import GlossarioRifiutato, decidi_voce
from app.migrations import PASSI, migra
from app.risposte import domanda_sul_fascicolo

FORNO = "La resistente ha contestato la fornitura?"


def test_con_il_glossario_parte_il_promemoria(app, civile):
    modello = ModelloCheRicorda()
    with app.state.session_factory() as db:
        sarti, fascicolo = utente(db, "sarti"), db.get(Fascicolo, civile.id)
        prima = domanda_sul_fascicolo(db, sarti, fascicolo, FORNO, modello)
        decidi_voce(db, sarti, fascicolo, "fornitura", ["forno"])
        dopo = domanda_sul_fascicolo(db, sarti, fascicolo, FORNO, modello)
    assert "promemoria.docx" not in {p.documento for p in prima.passi}
    assert "promemoria.docx" in {p.documento for p in dopo.passi}
    assert f"DOMANDA: {FORNO}\n" in modello.ricevuti[-1]  # parte com'era


def test_lo_decide_l_avvocato_del_fascicolo(app, civile):
    with app.state.session_factory() as db:
        fascicolo = db.get(Fascicolo, civile.id)
        for nome in ("irene", "dini"):
            with pytest.raises(GlossarioRifiutato, match="l'avvocato"):
                decidi_voce(
                    db, utente(db, nome), fascicolo, "fornitura", ["forno"]
                )
        sarti = utente(db, "sarti")
        with pytest.raises(GlossarioRifiutato, match="quattro lettere"):
            decidi_voce(db, sarti, fascicolo, "fornitura", ["PEC"])
        decidi_voce(db, sarti, fascicolo, "fornitura", ["forno", "cucina"])
        assert decidi_voce(db, sarti, fascicolo, "fornitura", []) == {}
        eventi = list(
            db.scalars(select(Evento).where(Evento.azione == "glossario"))
        )
    assert json.loads(eventi[0].dettaglio)["equivalenti"] == [
        "forno",
        "cucina",
    ]


def test_il_comando(app, civile, capsys):
    with app.state.session_factory() as db:
        manage.glossario_dalla_riga(
            db,
            Namespace(
                codice="2026-071",
                parola="fornitura",
                equivalenti=["forno"],
                da="sarti",
            ),
        )
        manage.glossario_dalla_riga(
            db,
            Namespace(
                codice="2026-071", parola=None, equivalenti=[], da="irene"
            ),
        )
    righe = capsys.readouterr().out.splitlines()
    assert (
        righe
        == [
            "Il glossario di 2026-071: 1 voce.",
            "  fornitura: forno",
        ]
        * 2
    )


def test_la_migrazione_12_aggiunge_il_glossario(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in range(1, 12)})  # la versione 1.1.2
        migra(engine)
        PASSI[12] = tutti[12]  # arriva la versione 1.2
        assert migra(engine) == [12]
        with engine.connect() as conn:
            colonne = {
                c["name"] for c in inspect(conn).get_columns("fascicoli")
            }
        assert "glossario" in colonne
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
