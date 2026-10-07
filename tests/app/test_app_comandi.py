"""I comandi di amministrazione: utenti, fascicoli di prova, diagnosi."""

from __future__ import annotations

import pytest
from aiuti import con_fascicoli
from sqlalchemy import select

from app import manage
from app.db import Assegnazione, Fascicolo, Utente


def test_i_fascicoli_di_prova_vanno_all_avvocato_della_materia(app):
    fascicoli = con_fascicoli(app)
    with app.state.session_factory() as db:
        nomi = {u.id: u.nome for u in db.scalars(select(Utente))}
        assegnati = {
            f.codice: {
                nomi[a]
                for a in db.scalars(
                    select(Assegnazione.utente_id).where(
                        Assegnazione.fascicolo_id == f.id
                    )
                )
            }
            for f in db.scalars(select(Fascicolo))
        }
    assert nomi[fascicoli["2026-072"].avvocato_id] == "Paola Righi"
    assert assegnati["2026-071"] == {"Elena Sarti", "Irene", "Rosa"}
    assert assegnati["2026-073"] == {"Stefano Valli", "Rosa"}


def test_i_fascicoli_di_prova_non_si_rifanno(app):
    con_fascicoli(app)
    with app.state.session_factory() as db:
        with pytest.raises(manage.CommandError, match="già fascicoli"):
            manage.crea_prova(db, production=False)


def test_la_diagnosi_non_mostra_i_segreti(
    app, impostazioni, monkeypatch, capsys
):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-prova-da-non-mostrare")
    assert manage.diagnosi(impostazioni, app.state.engine) == 0
    uscita = capsys.readouterr().out
    assert "in OPENAI_API_KEY (non mostrata)" in uscita
    assert "sk-prova" not in uscita
    assert impostazioni.secret_key not in uscita
