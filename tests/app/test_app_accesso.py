"""REQ-01: si accede con nome utente e passphrase; nessuna registrazione."""

from __future__ import annotations

import pytest
from aiuti import accedi, invia

from app.manage import CommandError, crea_utente, imposta_attivo
from app.security import COOKIE_SESSIONE


def test_si_entra_con_la_passphrase_giusta(browser):
    client = browser()
    risposta = accedi(client, "sarti")
    assert risposta.status_code == 303
    assert risposta.headers["location"] == "/fascicoli"
    assert COOKIE_SESSIONE in risposta.cookies


def test_la_passphrase_sbagliata_non_dice_che_cosa_era_sbagliato(browser):
    client = browser()
    sbagliata = accedi(client, "sarti", "una passphrase sbagliata")
    inesistente = accedi(client, "nessuno", "una passphrase qualunque")
    for risposta in (sbagliata, inesistente):
        assert risposta.status_code == 401
        assert "Nome utente o passphrase non validi." in risposta.text


def test_una_passphrase_corta_non_si_puo_creare(app):
    with app.state.session_factory() as db:
        with pytest.raises(CommandError, match="almeno 15 caratteri"):
            crea_utente(db, "marco", "avvocato", "Marco Dini", "troppo corta")


def test_non_esiste_una_pagina_di_registrazione(browser):
    client = browser()
    assert client.get("/registrazione").status_code == 404


def test_senza_sessione_si_torna_all_accesso(browser):
    risposta = browser().get("/fascicoli", follow_redirects=False)
    assert risposta.status_code == 303
    assert risposta.headers["location"] == "/accesso"


def test_un_account_disattivato_non_entra_piu(app, browser):
    client = browser("irene")
    with app.state.session_factory() as db:
        imposta_attivo(db, "irene", False)
    # La sessione aperta è chiusa, e un nuovo accesso è rifiutato.
    assert client.get("/fascicoli", follow_redirects=False).status_code == 303
    assert accedi(browser(), "irene").status_code == 401


def test_dopo_dieci_errori_si_aspetta(browser):
    client = browser()
    for _ in range(10):
        assert (
            accedi(client, "rosa", "passphrase sbagliata!!").status_code == 401
        )
    assert accedi(client, "rosa").status_code == 429


def test_uscire_chiude_la_sessione(browser):
    client = browser("sarti")
    assert invia(client, "/uscita", {}).status_code == 303
    assert client.get("/fascicoli", follow_redirects=False).status_code == 303
