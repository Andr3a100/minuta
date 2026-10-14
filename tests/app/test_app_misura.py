"""La misura dopo l'avvio e il sostituto nel fascicolo (lezione 38)."""

from __future__ import annotations

import json

import pytest
from aiuti import con_fascicoli
from sqlalchemy import select
from test_app_bozze import civile, con_scadenza, utente  # noqa: F401

from app import manage, misura
from app.db import Assegnazione, Bozza, Evento, Fascicolo, Scadenza, UsoAI
from app.misura import Misura, MisuraRifiutata, registra_tempo, verdetto
from app.muri import MuroRifiutato, assegna, imposta_materie

PARTENZA = misura.carica_partenza()


def fascicolo(db, codice):
    return db.scalar(select(Fascicolo).where(Fascicolo.codice == codice))


def test_i_tempi_si_registrano_con_le_loro_regole(app):
    con_fascicoli(app)
    with app.state.session_factory() as db:
        f, irene = fascicolo(db, "2026-071"), utente(db, "irene")
        with pytest.raises(MisuraRifiutata, match="attività"):
            registra_tempo(db, irene, f, "pausa", 10)
        with pytest.raises(MisuraRifiutata, match="da 1 a 1440"):
            registra_tempo(db, irene, f, "studio", 0)
        registra_tempo(db, irene, f, "studio", 50)
        registra_tempo(db, irene, f, "studio", 30)
        registra_tempo(db, utente(db, "sarti"), f, "rilettura", 12)
        riga = db.scalar(select(Evento).where(Evento.azione == "tempo"))
        assert json.loads(riga.dettaglio) == {
            "attivita": "studio",
            "minuti": 50,
        }
        oggi = misura.misura_di_oggi(db)
    assert oggi.fascicoli == ["2026-071"]
    assert oggi.minuti == {"studio": [80], "stesura": [], "rilettura": [12]}


def test_solo_rilettura_non_fa_un_fascicolo_misurato(app):
    con_fascicoli(app)
    with app.state.session_factory() as db:
        registra_tempo(
            db, utente(db, "sarti"), fascicolo(db, "2026-071"), "rilettura", 9
        )
        oggi = misura.misura_di_oggi(db)
    assert oggi.fascicoli == []
    assert oggi.minuti["rilettura"] == []


def test_scadenze_ed_errori_vengono_da_minuta(app, civile):  # noqa: F811
    with app.state.session_factory() as db:
        sarti = utente(db, "sarti")
        f = db.get(Fascicolo, civile.id)
        registra_tempo(db, sarti, f, "studio", 70)
        oggi = misura.misura_di_oggi(db)
        assert (oggi.documentate, oggi.con_errori) == (1, 0)
        scadenza = db.scalar(select(Scadenza))
        scadenza.confermata_da_id = None
        db.commit()
        assert misura.misura_di_oggi(db).documentate == 0
        voce = UsoAI(
            utente_id=sarti.id,
            fascicolo_id=f.id,
            modello="prova",
            categorie="",
            scopo="prova",
            impronta="0" * 64,
            caratteri=0,
            controllo="",
        )
        db.add(voce)
        db.flush()
        for modifiche in ({"stile": 3, "dati": 0}, {"dati": 1}):
            assert misura.misura_di_oggi(db).con_errori == 0
            db.add(
                Bozza(
                    fascicolo_id=f.id,
                    tipo="opposizione",
                    paragrafi="[]",
                    note="[]",
                    uso_ai_id=voce.id,
                    preparata_da_id=sarti.id,
                    modifiche=json.dumps(modifiche),
                )
            )
        db.commit()
        assert misura.misura_di_oggi(db).con_errori == 1


def test_il_verdetto_della_lezione_2():
    cinque = [f"2026-0{n}" for n in range(81, 86)]
    poche = Misura(cinque[:4], {"studio": [70] * 4}, 4, 0)
    assert verdetto(PARTENZA, poche) == [
        "Fascicoli misurati: 4; la misura di partenza ne ha 5. "
        "Nessun confronto, ancora."
    ]
    buona = Misura(cinque, {"studio": [60, 70, 80, 85, 100]}, 5, 2)
    assert verdetto(PARTENZA, buona)[-1] == "Obiettivo raggiunto."
    # La scorciatoia: più veloci, ma più errori trovati in revisione.
    veloce = Misura(cinque, {"studio": [40, 45, 50, 55, 60]}, 5, 4)
    esito = verdetto(PARTENZA, veloce)
    assert "tempo mediano di studio: sì" in esito
    assert "errori in revisione non cresciuti: no" in esito
    assert esito[-1].startswith("Obiettivo non raggiunto")
    lenta = Misura(cinque, {"studio": [90] * 5}, 5, 0)
    assert "tempo mediano di studio: no" in verdetto(PARTENZA, lenta)
    senza = Misura(cinque, {"studio": [60] * 5}, 4, 0)
    assert "scadenze documentate: no" in verdetto(PARTENZA, senza)


def test_il_sostituto_entra_con_le_regole_dei_muri(app):
    con_fascicoli(app)
    with app.state.session_factory() as db:
        f = fascicolo(db, "2026-071")
        sarti, dini, irene = (
            utente(db, n) for n in ("sarti", "dini", "irene")
        )
        with pytest.raises(MuroRifiutato, match="avvocato del fascicolo"):
            assegna(db, irene, f, dini)
        with pytest.raises(MuroRifiutato, match="avvocato del fascicolo"):
            assegna(db, dini, f, dini)
        valli = utente(db, "valli")
        imposta_materie(db, sarti, valli, ["penale"])
        with pytest.raises(MuroRifiutato, match="materia civile"):
            assegna(db, sarti, f, valli)
        assegna(db, sarti, f, dini)
        assert db.scalar(
            select(Assegnazione).where(
                Assegnazione.fascicolo_id == f.id,
                Assegnazione.utente_id == dini.id,
            )
        )
        with pytest.raises(MuroRifiutato, match="lavora già"):
            assegna(db, sarti, f, dini)


def test_il_comando_della_misura(app, capsys):
    con_fascicoli(app)
    with app.state.session_factory() as db:
        registra_tempo(
            db, utente(db, "irene"), fascicolo(db, "2026-071"), "studio", 75
        )
        manage.misura_dalla_riga(db)
    uscita = capsys.readouterr().out
    assert "  minuti di studio          126 / 125       75 / 75" in uscita
    assert "  minuti di rilettura       non misurata    non misurata" in uscita
    assert "  scadenze documentate      40%             0%" in uscita
    assert "Con i minuti di studio: 2026-071." in uscita
    assert "Nessun confronto, ancora." in uscita
