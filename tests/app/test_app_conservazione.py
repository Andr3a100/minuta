"""Quanto si conservano i fascicoli, e come si cancellano (lezione 33)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from aiuti import con_fascicoli
from sqlalchemy import func, inspect, select

from app import documenti as app_documenti
from app.conservazione import (
    ConservazioneRifiutata,
    cancella_fascicolo,
    carica_regola,
    chiuso_il,
    fascicoli_chiusi,
    fino_al,
    passa_di_stato,
    residui,
)
from app.copie import fai_copia
from app.db import Base, Evento, Fascicolo, Segnaposto, UsoAI, Utente, adesso
from app.invio import aggiungi_persona

RADICE = Path(__file__).resolve().parents[2]
PROVA = RADICE / "documenti-di-prova"
REGOLA = carica_regola()
OGGI = adesso().date()


def utente(db, nome):
    return db.scalar(select(Utente).where(Utente.nome_utente == nome))


def fascicolo(db, codice):
    return db.scalar(select(Fascicolo).where(Fascicolo.codice == codice))


def chiudi(db, codice, chi="sarti"):
    for stato in ("in_studio", "deciso", "chiuso"):
        passa_di_stato(db, utente(db, chi), fascicolo(db, codice), stato)


@pytest.fixture
def studio(app, impostazioni, tmp_path):
    """I fascicoli di prova; nel 071 due documenti, uno dei quali anche
    nel 072, e una persona nell'elenco."""
    con_fascicoli(app)
    settings = replace(impostazioni, copie_dir=str(tmp_path / "copie"))
    with app.state.session_factory() as db:
        sarti = utente(db, "sarti")
        primo, secondo = fascicolo(db, "2026-071"), fascicolo(db, "2026-072")
        decreto = (PROVA / "2026-074" / "decreto.pdf").read_bytes()
        ricorso = (PROVA / "2026-071" / "ricorso.pdf").read_bytes()
        app_documenti.carica(
            db, settings, sarti, primo, "decreto.pdf", decreto
        )
        app_documenti.carica(
            db, settings, sarti, primo, "ricorso.pdf", ricorso
        )
        app_documenti.carica(db, settings, sarti, secondo, "d.pdf", decreto)
        aggiungi_persona(db, sarti, primo, "Mario Bianchi", "testimone")
        db.add(Segnaposto(fascicolo_id=primo.id, segno="[P1]", valore="Mario"))
        db.commit()
    return settings


def test_il_passaggio_di_stato_ha_le_sue_regole(app, studio):
    with app.state.session_factory() as db:
        f = fascicolo(db, "2026-071")
        with pytest.raises(ConservazioneRifiutata, match="non previsto"):
            passa_di_stato(db, utente(db, "sarti"), f, "chiuso")
        passa_di_stato(db, utente(db, "irene"), f, "in_studio")
        with pytest.raises(ConservazioneRifiutata, match="ruolo"):
            passa_di_stato(db, utente(db, "irene"), f, "deciso")
        assert chiuso_il(db, f) is None
        passa_di_stato(db, utente(db, "sarti"), f, "deciso")
        passa_di_stato(db, utente(db, "sarti"), f, "chiuso")
        assert chiuso_il(db, f) == OGGI
        assert f.versione == 4


def test_conta_l_ultima_chiusura(app, studio):
    with app.state.session_factory() as db:
        chiudi(db, "2026-071")
        f = fascicolo(db, "2026-071")
        prima = db.scalar(
            select(Evento)
            .where(Evento.azione == "stato")
            .order_by(Evento.id.desc())
        )
        prima.creato_il = prima.creato_il - timedelta(days=400)
        db.commit()
        assert chiuso_il(db, f) == OGGI - timedelta(days=400)
        passa_di_stato(db, utente(db, "sarti"), f, "aperto")
        assert chiuso_il(db, f) is None
        for stato in ("in_studio", "deciso", "chiuso"):
            passa_di_stato(db, utente(db, "sarti"), f, stato)
        assert chiuso_il(db, f) == OGGI


def test_la_regola_dello_studio():
    assert fino_al(date(2026, 10, 14), REGOLA) == date(2036, 10, 14)
    assert fino_al(date(2028, 2, 29), REGOLA) == date(2038, 2, 28)
    da_decidere = {"fascicoli": {"anni": "da decidere"}}
    assert fino_al(date(2026, 10, 14), da_decidere) is None


def test_prima_del_termine_non_si_cancella(app, studio):
    with app.state.session_factory() as db:
        f = fascicolo(db, "2026-071")
        sarti = utente(db, "sarti")
        with pytest.raises(ConservazioneRifiutata, match="non è chiuso"):
            cancella_fascicolo(db, studio, sarti, f, REGOLA, OGGI)
        chiudi(db, "2026-071")
        with pytest.raises(ConservazioneRifiutata, match="suo avvocato"):
            cancella_fascicolo(db, studio, utente(db, "dini"), f, REGOLA, OGGI)
        dieci = fino_al(OGGI, REGOLA)
        with pytest.raises(ConservazioneRifiutata, match="si cancella dal"):
            cancella_fascicolo(
                db, studio, sarti, f, REGOLA, dieci - timedelta(days=1)
            )
        da_decidere = {**REGOLA, "fascicoli": {"anni": "da decidere"}}
        with pytest.raises(ConservazioneRifiutata, match="non ha deciso"):
            cancella_fascicolo(db, studio, sarti, f, da_decidere, dieci)
        assert [c.codice for c in fascicoli_chiusi(db, REGOLA)] == ["2026-071"]
        assert fascicoli_chiusi(db, REGOLA)[0].fino_al == dieci


def righe_del_fascicolo(db, id_):
    """Quante righe di ogni tabella rimandano ancora al fascicolo."""
    contate = {}
    for tabella in Base.metadata.sorted_tables:
        if "fascicolo_id" in tabella.c:
            n = db.scalar(
                select(func.count())
                .select_from(tabella)
                .where(tabella.c.fascicolo_id == id_)
            )
            if n:
                contate[tabella.name] = n
    return contate


def test_la_cancellazione_toglie_tutto_e_lascia_il_resto(app, studio):
    with app.state.session_factory() as db:
        f = fascicolo(db, "2026-071")
        id_ = f.id
        sarti = utente(db, "sarti")
        db.add(
            UsoAI(
                utente_id=sarti.id,
                fascicolo_id=id_,
                modello="finto",
                categorie="",
                scopo="prova",
                impronta="0" * 64,
                caratteri=1,
                controllo="",
            )
        )
        db.commit()
        chiudi(db, "2026-071")
        assert righe_del_fascicolo(db, id_)
        dieci = fino_al(OGGI, REGOLA)
        tolti = cancella_fascicolo(db, studio, sarti, f, REGOLA, dieci)
        assert righe_del_fascicolo(db, id_) == {}
        assert fascicolo(db, "2026-071") is None
        # Il ricorso era soltanto qui; il decreto anche nel 2026-072.
        assert len(tolti) == 1
        trovati = residui(db, studio, REGOLA)
        assert trovati.file_senza_documento == []
        assert trovati.documenti_senza_file == []
        # Il registro dell'uso dell'AI resta, senza il fascicolo.
        voce = db.scalar(select(UsoAI))
        assert voce.fascicolo_id is None
        riga = db.scalar(
            select(Evento).where(Evento.azione == "cancellazione")
        )
        assert json.loads(riga.dettaglio)["codice"] == "2026-071"
        assert riga.fascicolo_id is None
        assert fascicolo(db, "2026-072") is not None


def test_ogni_tabella_con_un_fascicolo_e_nella_cancellazione(app):
    """Una tabella nuova con un fascicolo deve entrare nella cancellazione:
    se no, le sue righe fermerebbero la cancellazione o resterebbero."""
    nomi = {
        t.name for t in Base.metadata.sorted_tables if "fascicolo_id" in t.c
    }
    noti = {
        "correzioni",
        "scadenze",
        "verifiche",
        "schede",
        "bozze",
        "risposte",
        "segnaposto",
        "persone",
        "documenti",
        "assegnazioni",
        "eventi",
        "uso_ai",
    }
    assert nomi == noti
    assert inspect(app.state.engine).has_table("fascicoli")


def test_i_residui_e_le_copie(app, studio):
    with app.state.session_factory() as db:
        fai_copia(studio, 30, OGGI)
        chiudi(db, "2026-073")
        f = fascicolo(db, "2026-073")
        avvocato = db.get(Utente, f.avvocato_id)
        dieci = fino_al(OGGI, REGOLA)
        cancella_fascicolo(db, studio, avvocato, f, REGOLA, dieci)
        trovati = residui(db, studio, REGOLA)
        assert trovati.nelle_copie == [
            ("2026-073", 1, OGGI + timedelta(days=31))
        ]
        # Un originale che nessun documento usa si vede.
        orfano = Path(studio.data_dir) / "documenti" / ("f" * 64)
        orfano.write_bytes(b"resto")
        assert residui(db, studio, REGOLA).file_senza_documento == ["f" * 64]
