"""REQ-02: avvocato, praticante, segreteria, e che cosa può fare ciascuno."""

from __future__ import annotations

import pytest
from aiuti import con_fascicoli, invia

from app.registro import RichiestaNonAmmessa, chiedi

NUOVO = {
    "codice": "2026-090",
    "cliente": "Cliente inventato S.r.l.",
    "materia": "civile",
    "oggetto": "Prova di apertura",
}


def avvocato_id(app, nome: str) -> int:
    from sqlalchemy import select

    from app.db import Utente

    with app.state.session_factory() as db:
        return db.scalar(select(Utente.id).where(Utente.nome == nome))


def test_la_segreteria_apre_un_fascicolo(app, browser):
    dati = {**NUOVO, "avvocato_id": str(avvocato_id(app, "Elena Sarti"))}
    risposta = invia(browser("rosa"), "/fascicoli/nuovo", dati)
    assert risposta.status_code == 303


def test_il_praticante_non_apre_fascicoli(app, browser):
    dati = {**NUOVO, "avvocato_id": str(avvocato_id(app, "Elena Sarti"))}
    assert invia(browser("irene"), "/fascicoli/nuovo", dati).status_code == 403


def passa(client, fascicolo, stato: str, versione: int):
    dati = {"stato": stato, "versione": str(versione)}
    indirizzo = f"/fascicoli/{fascicolo.id}/stato"
    return invia(client, indirizzo, dati, pagina=f"/fascicoli/{fascicolo.id}")


def test_il_praticante_studia_ma_non_decide(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    irene = browser("irene")
    assert passa(irene, civile, "in_studio", 1).status_code == 303
    assert passa(irene, civile, "deciso", 2).status_code == 403
    assert passa(browser("sarti"), civile, "deciso", 2).status_code == 303


def test_la_segreteria_non_cambia_lo_stato(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    assert passa(browser("rosa"), civile, "in_studio", 1).status_code == 403


def test_un_passaggio_che_non_esiste(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    assert passa(browser("sarti"), civile, "chiuso", 1).status_code == 422


class Eco:
    """Un modello finto che restituisce sempre la stessa risposta."""

    nome = "eco"

    def scrivi(self, sistema, richiesta):
        from minuta.model import Risposta

        return Risposta("ricevuto", self.nome, 10, 2)


def test_la_segreteria_non_fa_richieste_al_modello(app):
    from sqlalchemy import select

    from app.db import Utente

    with app.state.session_factory() as db:
        rosa = db.scalar(select(Utente).where(Utente.nome_utente == "rosa"))
        with pytest.raises(RichiestaNonAmmessa):
            chiedi(
                db,
                rosa,
                None,
                Eco(),
                "sistema",
                "domanda",
                scopo="prova",
                categorie="nessuna",
                controllo="nessuno",
            )
