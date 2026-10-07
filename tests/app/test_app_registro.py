"""REQ-04: i due registri, e la transazione che li tiene veri."""

from __future__ import annotations

import hashlib

import pytest
from aiuti import con_fascicoli, invia
from sqlalchemy import func, select

from app import web
from app.db import Evento, Fascicolo, UsoAI, Utente
from app.registro import chiedi
from minuta.model import Risposta


def test_ogni_cambio_di_stato_lascia_la_sua_riga(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    pagina = f"/fascicoli/{civile.id}"
    dati = {"stato": "in_studio", "versione": "1"}
    invia(browser("irene"), f"{pagina}/stato", dati, pagina=pagina)
    with app.state.session_factory() as db:
        riga = db.scalars(select(Evento).where(Evento.azione == "stato")).one()
        irene = db.scalar(select(Utente).where(Utente.nome_utente == "irene"))
    assert riga.utente_id == irene.id
    assert riga.fascicolo_id == civile.id
    assert '"dopo": "in_studio"' in riga.dettaglio


# [libro:prova-transazione]
def test_senza_la_sua_riga_la_modifica_non_resta(app, browser, monkeypatch):
    civile = con_fascicoli(app)["2026-071"]

    def guasto(*args, **kwargs):
        raise RuntimeError("guasto simulato mentre si scrive il registro")

    irene = browser("irene")  # entra prima del guasto: anche l'accesso scrive
    monkeypatch.setattr("app.routes.registra_evento", guasto)
    pagina = f"/fascicoli/{civile.id}"
    dati = {"stato": "in_studio", "versione": "1"}
    with pytest.raises(RuntimeError, match="guasto simulato"):
        invia(irene, f"{pagina}/stato", dati, pagina=pagina)
    # La modifica e la sua riga stanno nella stessa transazione:
    # se la riga non si scrive, lo stato resta quello di prima.
    with app.state.session_factory() as db:
        fascicolo = db.get(Fascicolo, civile.id)
        assert (fascicolo.stato, fascicolo.versione) == ("aperto", 1)


# [/libro:prova-transazione]


class Eco:
    nome = "gpt-6.1-sol"  # un nome con i prezzi in config/prezzi.json

    def scrivi(self, sistema, richiesta):
        return Risposta("ricevuto", self.nome, 1000, 200)


def test_la_voce_dice_chi_e_mai_che_cosa(app):
    civile = con_fascicoli(app)["2026-071"]
    domanda = "Riassumi il decreto di [SOGGETTO_1] in tre righe."
    with app.state.session_factory() as db:
        irene = db.scalar(select(Utente).where(Utente.nome_utente == "irene"))
        _, voce = chiedi(
            db,
            irene,
            civile,
            Eco(),
            "Sei un assistente.",
            domanda,
            scopo="riassunto",
            categorie="comuni",
            controllo="letto dall'avvocato",
        )
        db.commit()
        salvata = db.get(UsoAI, voce.id)
        valori = [str(getattr(salvata, c.name)) for c in UsoAI.__table__.c]
    inviato = "Sei un assistente.\n\n" + domanda
    assert salvata.utente_id == irene.id  # chi, che il pilota non sapeva
    assert salvata.impronta == hashlib.sha256(inviato.encode()).hexdigest()
    assert salvata.caratteri == len(inviato)
    assert salvata.costo_usd == round((1000 * 2.00 + 200 * 10.00) / 1e6, 6)
    assert not any("decreto" in valore for valore in valori)  # mai il testo


def test_senza_salvataggio_la_voce_non_resta(app):
    with app.state.session_factory() as db:
        sarti = db.scalar(select(Utente).where(Utente.nome_utente == "sarti"))
        chiedi(
            db,
            sarti,
            None,
            Eco(),
            "s",
            "d",
            scopo="prova",
            categorie="nessuna",
            controllo="nessuno",
        )
        db.rollback()  # l'azione che l'aveva chiesta non è andata a buon fine
        assert db.scalar(select(func.count()).select_from(UsoAI)) == 0


def test_le_righe_del_registro_non_si_scrivono_da_sole(app):
    # registra_evento aggiunge la riga alla transazione, non la salva.
    with app.state.session_factory() as db:
        web.registra_evento(db, None, None, "prova")
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Evento)) == 5
