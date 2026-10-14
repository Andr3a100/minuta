"""Le misure della valutazione d'impatto, controllate (lezione 35)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from aiuti import con_fascicoli
from sqlalchemy import select

from app import impatto, manage
from app.conservazione import passa_di_stato
from app.copie import fai_copia
from app.db import Fascicolo, UsoAI, Utente
from app.informativa import registra_consegna
from app.muri import imposta_materie

OGGI = date(2026, 10, 14)


def utente(db, nome):
    return db.scalar(select(Utente).where(Utente.nome_utente == nome))


@pytest.fixture
def studio(app, impostazioni, tmp_path):
    con_fascicoli(app)
    return replace(impostazioni, copie_dir=str(tmp_path / "copie"))


def per_misura(db, settings):
    return {e.misura: e for e in impatto.esamina(db, settings)}


def test_il_muro_del_penale_si_controlla_sulle_assegnazioni(app, studio):
    with app.state.session_factory() as db:
        m3 = per_misura(db, studio)["M3"]
        assert m3.stato == impatto.SMENTITA
        # Chi apre e l'avvocato del fascicolo, senza materie dichiarate.
        assert "Rosa in 2026-073" in m3.dettaglio
        assert "Stefano Valli in 2026-073" in m3.dettaglio
        valli = utente(db, "valli")
        imposta_materie(db, valli, valli, ["penale"])
        imposta_materie(db, valli, utente(db, "rosa"), ["civile", "penale"])
        assert per_misura(db, studio)["M3"].stato == impatto.VERIFICATA


def test_il_registro_dice_se_qualcosa_è_uscito(app, studio):
    with app.state.session_factory() as db:
        assert per_misura(db, studio)["M2"].stato == impatto.VERIFICATA
        f = db.scalar(select(Fascicolo).where(Fascicolo.codice == "2026-071"))
        for controllo in (
            "elenco di 3 persone; fughe: 0; nomi fuori elenco: 0",
            "elenco di 3 persone; fughe: 0; nomi fuori elenco: 2",
        ):
            db.add(
                UsoAI(
                    utente_id=utente(db, "sarti").id,
                    fascicolo_id=f.id,
                    modello="finto",
                    categorie="",
                    scopo="prova",
                    impronta="0" * 64,
                    caratteri=1,
                    controllo=controllo,
                )
            )
        db.commit()
        m2 = per_misura(db, studio)["M2"]
        assert m2.stato == impatto.SMENTITA
        assert m2.dettaglio.endswith("n. 2")


def test_le_copie_si_ripristinano(app, studio):
    with app.state.session_factory() as db:
        assert per_misura(db, studio)["M4"].dettaglio == "nessuna copia"
        copia = fai_copia(studio, 30, OGGI).percorso
        assert per_misura(db, studio)["M4"].stato == impatto.VERIFICATA
        copia.write_bytes(copia.read_bytes()[:100])
        m4 = per_misura(db, studio)["M4"]
        assert m4.stato == impatto.SMENTITA
        assert "non si ripristina" in m4.dettaglio


def test_conservazione_decisa_e_senza_residui(app, studio, monkeypatch):
    with app.state.session_factory() as db:
        assert per_misura(db, studio)["M5"].stato == impatto.VERIFICATA
        orfano = Path(studio.data_dir) / "documenti" / ("a" * 64)
        orfano.parent.mkdir(parents=True, exist_ok=True)
        orfano.write_bytes(b"resto")
        assert per_misura(db, studio)["M5"].stato == impatto.SMENTITA
        orfano.unlink()
        regola = impatto.carica_regola()
        regola["fascicoli"]["anni"] = "da decidere"
        monkeypatch.setattr(impatto, "carica_regola", lambda: regola)
        m5 = per_misura(db, studio)["M5"]
        assert (m5.stato, m5.dettaglio) == (
            impatto.SMENTITA,
            "la regola dei fascicoli è ancora da decidere",
        )


def test_informativa_e_comando(app, studio, capsys):
    with app.state.session_factory() as db:
        f = db.scalar(select(Fascicolo).where(Fascicolo.codice == "2026-071"))
        registra_consegna(db, utente(db, "rosa"), f, OGGI, "PEC")
        m1 = per_misura(db, studio)["M1"]
        assert "l'informativa di oggi: 1 su 3;" in m1.dettaglio
        assert manage.impatto_dalla_riga(db, studio) == 1
        assert "La valutazione non vale: smentite M3, M4." in (
            capsys.readouterr().out
        )
        valli = utente(db, "valli")
        imposta_materie(db, valli, valli, ["penale"])
        imposta_materie(db, valli, utente(db, "rosa"), ["penale"])
        fai_copia(studio, 30, OGGI)
        assert manage.impatto_dalla_riga(db, studio) == 0
        uscita = capsys.readouterr().out
        assert "M9 alfabetizzazione: a mano" in uscita
        assert "Nessuna misura smentita" in uscita


def test_i_fascicoli_chiusi_non_contano(app, studio):
    with app.state.session_factory() as db:
        f = db.scalar(select(Fascicolo).where(Fascicolo.codice == "2026-072"))
        avvocato = db.get(Utente, f.avvocato_id)
        for stato in ("in_studio", "deciso", "chiuso"):
            passa_di_stato(db, avvocato, f, stato)
        assert "0 su 2;" in per_misura(db, studio)["M1"].dettaglio
