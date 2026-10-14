"""I muri dello studio, fra le materie e fra i clienti (lezione 32)."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest
from aiuti import con_fascicoli, invia
from sqlalchemy import inspect, select

from app import manage
from app.db import Assegnazione, Evento, Fascicolo, Utente, make_engine
from app.invio import aggiungi_persona
from app.migrations import PASSI, migra
from app.muri import MuroRifiutato, conflitti, imposta_materie, normale


def utente(db, nome_utente):
    return db.scalar(select(Utente).where(Utente.nome_utente == nome_utente))


def apri(db, codice, cliente, materia, avvocato, da, praticante=None, **altro):
    manage.apri_dalla_riga(
        db,
        Namespace(
            codice=codice,
            cliente=cliente,
            materia=materia,
            oggetto="Prova",
            avvocato=avvocato,
            praticante=praticante,
            da=da,
            **altro,
        ),
    )


@pytest.fixture
def studio(app):
    """I tre fascicoli di prova, con Termocucine controparte nel civile."""
    fascicoli = con_fascicoli(app)
    with app.state.session_factory() as db:
        aggiungi_persona(
            db,
            utente(db, "sarti"),
            db.get(Fascicolo, fascicoli["2026-071"].id),
            "Termocucine Secchia S.r.l.",
            "controparte",
        )
    return fascicoli


def test_le_materie_e_chi_c_era_gia(app, studio):
    with app.state.session_factory() as db:
        sarti, irene = utente(db, "sarti"), utente(db, "irene")
        with pytest.raises(MuroRifiutato, match="un avvocato"):
            imposta_materie(db, irene, irene, ["civile"])
        with pytest.raises(MuroRifiutato, match="sconosciuta: lavoro"):
            imposta_materie(db, sarti, irene, ["lavoro"])
        tolti = imposta_materie(db, sarti, irene, ["tributario"])
        assegnata = db.scalar(
            select(Assegnazione).where(Assegnazione.utente_id == irene.id)
        )
        assert imposta_materie(db, sarti, irene, []) == []  # tutte
    assert tolti == ["2026-071"] and assegnata is None


# [libro:prova-muri]
def test_il_penale_lo_vede_chi_ci_lavora(app, studio):
    with app.state.session_factory() as db:
        sarti = utente(db, "sarti")
        imposta_materie(db, sarti, utente(db, "irene"), ["civile"])
        imposta_materie(db, sarti, utente(db, "valli"), ["penale"])
        with pytest.raises(MuroRifiutato, match="Irene non lavora nella"):
            apri(
                db,
                "2026-076",
                "Bruno Ferretti",
                "penale",
                "valli",
                "rosa",
                praticante="irene",
            )
        with pytest.raises(MuroRifiutato, match="Stefano Valli non lavora"):
            apri(db, "2026-077", "Bruno Ferretti", "civile", "valli", "rosa")
        apri(db, "2026-076", "Bruno Ferretti", "penale", "valli", "rosa")


def test_un_conflitto_si_ferma_e_lo_valuta_un_avvocato(app, studio):
    with app.state.session_factory() as db:
        with pytest.raises(MuroRifiutato, match="2026-071 .Ristorazione"):
            apri(
                db,
                "2026-075",
                "termocucine secchia srl",
                "civile",
                "dini",
                "rosa",
            )
        with pytest.raises(MuroRifiutato, match="lo valuta un avvocato"):
            apri(
                db,
                "2026-075",
                "Termocucine Secchia S.r.l.",
                "civile",
                "dini",
                "rosa",
                conflitto_valutato="nessun conflitto",
            )
        apri(
            db,
            "2026-075",
            "Termocucine Secchia S.r.l.",
            "civile",
            "dini",
            "dini",
            conflitto_valutato="affare diverso, parere del consiglio",
        )
        evento = db.scalar(
            select(Evento).where(Evento.azione == "conflitto_valutato")
        )
    assert json.loads(evento.dettaglio)["valutazione"].startswith("affare")


# [/libro:prova-muri]


def test_anche_chi_entra_nell_elenco(app, studio):
    with app.state.session_factory() as db:
        valli = utente(db, "valli")
        riva = db.get(Fascicolo, studio["2026-073"].id)
        with pytest.raises(MuroRifiutato, match="2026-071"):
            aggiungi_persona(
                db, valli, riva, "Ristorazione Collinare S.r.l.", "testimone"
            )
        aggiungi_persona(
            db,
            valli,
            riva,
            "Ristorazione Collinare S.r.l.",
            "testimone",
            valutazione="testimone, non parte",
        )
        assert conflitti(db, "Ristorazione Collinare srl", "cliente") == [
            "2026-073 (Alessandro Riva), come testimone"
        ]
    assert normale("Termocucine Secchia S.r.l.") == normale(
        "termocucine  secchia srl"
    )


def test_nel_suo_fascicolo_il_cliente_non_e_in_conflitto(app, studio):
    with app.state.session_factory() as db:
        collinare = db.get(Fascicolo, studio["2026-071"].id)
        aggiungi_persona(
            db,
            utente(db, "sarti"),
            collinare,
            "Ristorazione Collinare srl",
            "debitrice",
        )


def test_il_browser_ferma_lo_stesso_conflitto(app, browser, studio):
    with app.state.session_factory() as db:
        dini = utente(db, "dini")
    risposta = invia(
        browser("rosa"),
        "/fascicoli/nuovo",
        {
            "codice": "2026-075",
            "cliente": "Termocucine Secchia S.r.l.",
            "materia": "civile",
            "oggetto": "Prova",
            "avvocato_id": str(dini.id),
            "praticante_id": "",
        },
        pagina="/fascicoli/nuovo",
    )
    assert risposta.status_code == 409
    assert "Possibile conflitto" in risposta.text


def test_il_comando_delle_materie(app, studio, capsys):
    with app.state.session_factory() as db:
        manage.materie_dalla_riga(
            db,
            Namespace(nome_utente="irene", materie=["tributario"], da="sarti"),
        )
        manage.materie_dalla_riga(
            db, Namespace(nome_utente="sarti", materie=[], da="sarti")
        )
    assert capsys.readouterr().out.splitlines() == [
        "Tolto dai fascicoli fuori dal muro: 2026-071.",
        "Le materie di Irene: tributario.",
        "Le materie di Elena Sarti: tutte.",
    ]


def test_la_migrazione_13_aggiunge_le_materie(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in range(1, 13)})
        migra(engine)
        PASSI[13] = tutti[13]
        assert migra(engine) == [13]
        with engine.connect() as conn:
            colonne = {c["name"] for c in inspect(conn).get_columns("utenti")}
        assert "materie" in colonne
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
