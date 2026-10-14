"""Il conto dello studio, con i prezzi misurati (lezione 36)."""

from __future__ import annotations

import pytest
from aiuti import con_fascicoli
from sqlalchemy import select

from app import conto, manage
from app.db import Fascicolo, UsoAI, Utente

DATI = conto.carica_conto()


def richiesta(db, codice, scopo):
    f = db.scalar(select(Fascicolo).where(Fascicolo.codice == codice))
    sarti = db.scalar(select(Utente).where(Utente.nome_utente == "sarti"))
    db.add(
        UsoAI(
            utente_id=sarti.id,
            fascicolo_id=f.id,
            modello="finto-deterministico",
            categorie="",
            scopo=scopo,
            impronta="0" * 64,
            caratteri=1,
            controllo="",
        )
    )
    db.commit()


def test_i_prezzi_sono_le_mediane_delle_chiamate_vere():
    prezzi = conto.prezzi_misurati(DATI)
    assert prezzi["bozza: opposizione"] == (pytest.approx(0.035051), 4)
    assert prezzi["bozza: promemoria"] == (0.014168, 1)
    assert prezzi["domanda sul fascicolo"] == (0.002988, 3)
    assert len(prezzi) == 6


def test_ogni_richiesta_al_prezzo_del_suo_tipo(app):
    con_fascicoli(app)
    prezzi = conto.prezzi_misurati(DATI)
    with app.state.session_factory() as db:
        richiesta(db, "2026-071", "scheda dell'atto in arrivo")
        richiesta(db, "2026-071", "bozza: opposizione")
        richiesta(db, "2026-071", "bozza: opposizione")
        richiesta(db, "2026-072", "riassunto")
        stime = {s.codice: s for s in conto.stima_per_fascicolo(db, prezzi)}
    assert stime["2026-071"].richieste == 3
    assert stime["2026-071"].dollari == round(0.009814 + 2 * 0.035051, 4)
    assert stime["2026-072"].dollari == 0
    assert stime["2026-072"].senza_prezzo == ["riassunto"]
    assert stime["2026-073"].richieste == 0


def test_il_ritorno_della_lezione_3():
    elenco, anno = conto.ritorno(DATI["ipotesi"])
    assert elenco == [-5600, -3200, -800, 1600, 4000]
    assert anno == 4
    peggio = {**DATI["ipotesi"], "minuti di rilettura": {"valore": 25}}
    assert conto.ritorno(peggio)[1] is None


def test_il_comando(app, capsys):
    con_fascicoli(app)
    with app.state.session_factory() as db:
        richiesta(db, "2026-071", "bozza: promemoria")
        assert manage.conto_dalla_riga(db) == 0
        uscita = capsys.readouterr().out
        assert "2026-071    1 richiesta   0,0142 dollari" in uscita
        assert "Pareggio: anno 4." in uscita
        richiesta(db, "2026-072", "riassunto")
        assert manage.conto_dalla_riga(db) == 1
        assert "senza prezzo misurato: riassunto" in capsys.readouterr().out
