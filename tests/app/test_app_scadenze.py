"""Le scadenze del fascicolo, nell'applicazione (lezione 19).

La data di partenza viene solo da una scheda confermata. Il decreto di
Ristorazione Collinare non la dice; la ricevuta della PEC sì.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from aiuti import con_fascicoli, invia
from sqlalchemy import func, inspect, select

from app import documenti as app_documenti
from app.db import Documento, Fascicolo, Scadenza, Utente, make_engine
from app.invio import aggiungi_persona
from app.migrations import PASSI, migra
from app.scadenze import ScadenzaRifiutata, conferma_scadenza, data_di_partenza
from minuta.model import ModelloFinto
from minuta.scheda import Riga

CARTELLA = (
    Path(__file__).resolve().parents[2] / "documenti-di-prova" / "2026-071"
)


@pytest.fixture
def civile(app, impostazioni):
    """Il fascicolo civile con il decreto e la ricevuta della PEC, e la
    controparte in elenco. Restituisce gli indirizzi dei due documenti."""
    app.state.modello = ModelloFinto()
    fascicolo = con_fascicoli(app)["2026-071"]
    indirizzi = {}
    with app.state.session_factory() as db:
        irene = db.scalar(select(Utente).where(Utente.nome_utente == "irene"))
        dentro = db.get(Fascicolo, fascicolo.id)
        aggiungi_persona(
            db, irene, dentro, "Termocucine Secchia S.r.l.", "controparte"
        )
        for nome in ("decreto.pdf", "ricevuta-pec.pdf"):
            documento, _ = app_documenti.carica(
                db,
                impostazioni,
                irene,
                dentro,
                nome,
                (CARTELLA / nome).read_bytes(),
            )
            indirizzi[nome] = (
                f"/fascicoli/{fascicolo.id}/documenti/{documento.id}"
            )
    return fascicolo, indirizzi


def quante_scadenze(app) -> int:
    with app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(Scadenza))


def scheda_confermata(irene, sarti, indirizzo, togliere=()):
    assert invia(irene, indirizzo + "/scheda", {}).status_code == 303
    for riga in togliere:
        invia(irene, indirizzo + "/scheda/togli", {"riga": riga})
    assert invia(sarti, indirizzo + "/scheda/conferma", {}).status_code == 303


def test_senza_una_scheda_confermata_non_si_calcola(app, browser, civile):
    _fascicolo, indirizzi = civile
    # La scheda c'è, ma nessun avvocato l'ha ancora confermata.
    invia(browser("irene"), indirizzi["ricevuta-pec.pdf"] + "/scheda", {})
    risposta = invia(
        browser("rosa"),
        indirizzi["ricevuta-pec.pdf"] + "/scadenza",
        {"termine": "opposizione al decreto ingiuntivo"},
    )
    assert risposta.status_code == 409
    assert "non è confermata" in risposta.text
    assert quante_scadenze(app) == 0


def test_dal_decreto_la_data_non_risulta(app, browser, civile):
    _fascicolo, indirizzi = civile
    irene, sarti = browser("irene"), browser("sarti")
    # Le righe sbagliate del modello finto, tolte come nella lezione 18.
    scheda_confermata(irene, sarti, indirizzi["decreto.pdf"], (1, 2, 4))
    risposta = invia(
        irene,
        indirizzi["decreto.pdf"] + "/scadenza",
        {"termine": "opposizione al decreto ingiuntivo"},
    )
    assert risposta.status_code == 409
    assert "non risulta dalla scheda" in risposta.text
    assert quante_scadenze(app) == 0


# [libro:prova-scadenza-app]
def test_dalla_ricevuta_la_scadenza_la_calcola_anche_la_segreteria(
    app, browser, civile
):
    fascicolo, indirizzi = civile
    irene, sarti, rosa = browser("irene"), browser("sarti"), browser("rosa")
    scheda_confermata(irene, sarti, indirizzi["ricevuta-pec.pdf"])
    risposta = invia(
        rosa,
        indirizzi["ricevuta-pec.pdf"] + "/scadenza",
        {"termine": "opposizione al decreto ingiuntivo"},
    )
    assert risposta.status_code == 303
    with app.state.session_factory() as db:
        scadenza = db.scalar(select(Scadenza))
    assert (scadenza.partenza, scadenza.scadenza) == (
        date(2026, 9, 21),
        date(2026, 11, 2),
    )
    assert scadenza.confermata_da_id is None  # da verificare
    conferma = f"/fascicoli/{fascicolo.id}/scadenze/{scadenza.id}/conferma"
    assert invia(rosa, conferma, {}).status_code == 403
    assert invia(sarti, conferma, {}).status_code == 303
    assert (
        "lunedì 2 novembre 2026"
        in sarti.get(f"/fascicoli/{fascicolo.id}").text
    )


# [/libro:prova-scadenza-app]


def test_una_scadenza_senza_data_non_si_conferma(app, civile):
    fascicolo, _ = civile
    with app.state.session_factory() as db:
        sarti = db.scalar(select(Utente).where(Utente.nome_utente == "sarti"))
        documento = db.scalar(select(Documento))
        scadenza = Scadenza(
            fascicolo_id=fascicolo.id,
            documento_id=documento.id,
            scheda_id=1,
            termine="opposizione al decreto ingiuntivo",
            norma="art. 641, primo comma, c.p.c.",
            partenza=date(2027, 6, 21),
            passaggi="[]",
            da_decidere="la proroga porta la scadenza in agosto",
            calcolata_da_id=sarti.id,
        )
        with pytest.raises(
            ScadenzaRifiutata, match="decisione è dell'avvocato"
        ):
            conferma_scadenza(
                db, sarti, db.get(Fascicolo, fascicolo.id), scadenza
            )


def test_la_conferma_e_dell_avvocato_anche_senza_il_browser(
    app, browser, civile
):
    fascicolo, indirizzi = civile
    scheda_confermata(
        browser("irene"), browser("sarti"), indirizzi["ricevuta-pec.pdf"]
    )
    invia(
        browser("rosa"),
        indirizzi["ricevuta-pec.pdf"] + "/scadenza",
        {"termine": "opposizione"},
    )
    with app.state.session_factory() as db:
        rosa = db.scalar(select(Utente).where(Utente.nome_utente == "rosa"))
        scadenza = db.scalar(select(Scadenza))
        with pytest.raises(ScadenzaRifiutata, match="Solo un avvocato"):
            conferma_scadenza(
                db, rosa, db.get(Fascicolo, fascicolo.id), scadenza
            )


def test_la_partenza_e_una_data_sola():
    righe = [
        Riga("date", "Data della notificazione: 21 settembre 2026", 1),
        Riga("date", "Data della notificazione: 22 settembre 2026", 1),
    ]
    with pytest.raises(ScadenzaRifiutata, match="più date"):
        data_di_partenza(righe)
    righe[1].tolta_da = "Elena Sarti"
    assert data_di_partenza(righe) == (date(2026, 9, 21), 1)
    with pytest.raises(ScadenzaRifiutata, match="non risulta"):
        data_di_partenza(
            [Riga("date", "Data della notificazione: non risulta", None)]
        )


def test_la_migrazione_5_aggiunge_le_scadenze(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in (1, 2, 3, 4)})  # la versione 0.4
        migra(engine)
        PASSI[5] = tutti[5]  # arriva la versione 0.5
        assert migra(engine) == [5]
        with engine.connect() as conn:
            assert inspect(conn).has_table("scadenze")
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
