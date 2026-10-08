"""Le verifiche dei documenti, nell'applicazione (lezione 20)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiuti import con_fascicoli, invia
from sqlalchemy import inspect, select

from app import documenti as app_documenti
from app.db import Fascicolo, Utente, Verifica, make_engine
from app.migrations import PASSI, migra
from app.verifiche import VerificaRifiutata, decidi_domanda, prepara_verifiche
from minuta.model import ModelloFinto

CARTELLA = (
    Path(__file__).resolve().parents[2] / "documenti-di-prova" / "2026-072"
)


@pytest.fixture
def tributario(app, impostazioni):
    """Il fascicolo di Ivo Marchetti con le due scansioni della cartella."""
    app.state.modello = ModelloFinto()
    fascicolo = con_fascicoli(app)["2026-072"]
    indirizzi = {}
    with app.state.session_factory() as db:
        righi = db.scalar(select(Utente).where(Utente.nome_utente == "righi"))
        for nome in ("cartella-scansione.pdf", "cartella-scansione-300.pdf"):
            documento, _ = app_documenti.carica(
                db,
                impostazioni,
                righi,
                db.get(Fascicolo, fascicolo.id),
                nome,
                (CARTELLA / nome).read_bytes(),
            )
            indirizzi[nome] = (
                f"/fascicoli/{fascicolo.id}/documenti/{documento.id}"
            )
    return fascicolo, indirizzi


def test_la_scansione_a_100_punti_non_torna(app, browser, tributario):
    _fascicolo, indirizzi = tributario
    righi = browser("righi")
    # Una scheda c'è, ma nessun avvocato l'ha confermata: niente fatti.
    invia(righi, indirizzi["cartella-scansione.pdf"] + "/scheda", {})
    indirizzo = indirizzi["cartella-scansione.pdf"] + "/verifiche"
    assert invia(righi, indirizzo, {"tipo": "cartella"}).status_code == 303
    pagina = righi.get(indirizzo).text
    assert "4.837,46, il totale dice 4.837,66: 0,20 di differenza" in pagina
    assert "la scheda non è confermata: nessun fatto" in pagina


def test_con_la_scheda_e_la_scadenza_le_domande_si_riempiono(
    app, browser, tributario
):
    _fascicolo, indirizzi = tributario
    righi, rosa = browser("righi"), browser("rosa")
    cartella = indirizzi["cartella-scansione-300.pdf"]
    invia(righi, cartella + "/scheda", {})
    for riga in (1, 2):
        invia(righi, cartella + "/scheda/togli", {"riga": riga})
    invia(righi, cartella + "/scheda/conferma", {})
    invia(rosa, cartella + "/scadenza", {"termine": "ricorso"})
    assert (
        invia(righi, cartella + "/verifiche", {"tipo": "cartella"}).status_code
        == 303
    )
    pagina = righi.get(cartella + "/verifiche").text
    assert "le 4 voci fanno il totale, 4.837,66" in pagina
    assert "Data della notificazione: 18 settembre 2026 (pagina 1)" in pagina
    assert "martedì 17 novembre 2026, da verificare" in pagina
    # Lo stato lo decide l'avvocato.
    assert (
        invia(
            rosa, cartella + "/verifiche/1", {"stato": "verificata"}
        ).status_code
        == 403
    )
    assert (
        invia(
            righi, cartella + "/verifiche/1", {"stato": "verificata"}
        ).status_code
        == 303
    )
    with app.state.session_factory() as db:
        domande = json.loads(db.scalar(select(Verifica)).domande)
    assert (domande[0]["stato"], domande[0]["deciso_da"]) == (
        "verificata",
        "Paola Righi",
    )
    assert domande[1]["stato"] == "aperta"


def test_le_regole_valgono_anche_senza_il_browser(app, browser, tributario):
    fascicolo, indirizzi = tributario
    invia(
        browser("righi"),
        indirizzi["cartella-scansione.pdf"] + "/verifiche",
        {"tipo": "cartella"},
    )
    with app.state.session_factory() as db:
        utenti = {u.nome_utente: u for u in db.scalars(select(Utente))}
        dentro = db.get(Fascicolo, fascicolo.id)
        verifica = db.scalar(select(Verifica))
        documento = verifica.documento_id
        with pytest.raises(VerificaRifiutata, match="segreteria"):
            prepara_verifiche(
                db,
                utenti["rosa"],
                dentro,
                db.get(app_documenti.Documento, documento),
                "cartella",
            )
        with pytest.raises(VerificaRifiutata, match="l'avvocato"):
            decidi_domanda(
                db, utenti["rosa"], dentro, verifica, 1, "verificata"
            )
        with pytest.raises(VerificaRifiutata, match="stati"):
            decidi_domanda(db, utenti["righi"], dentro, verifica, 1, "nulla")
        with pytest.raises(VerificaRifiutata, match="domanda 9"):
            decidi_domanda(
                db, utenti["righi"], dentro, verifica, 9, "verificata"
            )


def test_la_segreteria_non_prepara_le_verifiche(app, browser, tributario):
    _fascicolo, indirizzi = tributario
    indirizzo = indirizzi["cartella-scansione.pdf"] + "/verifiche"
    assert (
        invia(browser("rosa"), indirizzo, {"tipo": "cartella"}).status_code
        == 403
    )
    assert browser("rosa").get(indirizzo).status_code == 200


def test_la_migrazione_6_aggiunge_le_verifiche(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in range(1, 6)})  # la versione 0.5
        migra(engine)
        PASSI[6] = tutti[6]  # arriva la versione 0.6
        assert migra(engine) == [6]
        with engine.connect() as conn:
            assert inspect(conn).has_table("verifiche")
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
