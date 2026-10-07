"""REQ-03, prima parte: ciascuno vede solo i fascicoli a cui lavora."""

from __future__ import annotations

from aiuti import con_fascicoli, invia
from sqlalchemy import select

from app.db import Assegnazione, Utente


def test_ciascuno_vede_i_suoi_fascicoli(app, browser):
    con_fascicoli(app)
    elenco = browser("righi").get("/fascicoli").text
    assert "2026-072" in elenco  # il tributario è suo
    assert "2026-071" not in elenco and "2026-073" not in elenco


# [libro:prova-404]
def test_il_fascicolo_di_un_altro_risponde_404(app, browser):
    penale = con_fascicoli(app)["2026-073"]
    # Paola Righi non lavora al fascicolo penale: anche scrivendo
    # l'indirizzo a mano, per lei il fascicolo non esiste.
    risposta = browser("righi").get(f"/fascicoli/{penale.id}")
    assert risposta.status_code == 404
    assert browser("valli").get(f"/fascicoli/{penale.id}").status_code == 200


# [/libro:prova-404]


def test_chi_apre_e_chi_ci_lavora_sono_assegnati(app, browser):
    with app.state.session_factory() as db:
        sarti, irene, rosa = (
            db.scalar(select(Utente.id).where(Utente.nome_utente == n))
            for n in ("sarti", "irene", "rosa")
        )
    dati = {
        "codice": "2026-091",
        "cliente": "Cliente inventato S.r.l.",
        "materia": "civile",
        "oggetto": "Prova di apertura",
        "avvocato_id": str(sarti),
        "praticante_id": str(irene),
    }
    risposta = invia(browser("rosa"), "/fascicoli/nuovo", dati)
    assert risposta.status_code == 303
    numero = int(risposta.headers["location"].rsplit("/", 1)[1])
    with app.state.session_factory() as db:
        assegnati = set(
            db.scalars(
                select(Assegnazione.utente_id).where(
                    Assegnazione.fascicolo_id == numero
                )
            )
        )
    assert assegnati == {sarti, irene, rosa}


def test_i_campi_sbagliati_tornano_con_l_errore(app, browser):
    dati = {"codice": "41", "cliente": "", "materia": "lavoro", "oggetto": ""}
    risposta = invia(browser("rosa"), "/fascicoli/nuovo", dati)
    assert risposta.status_code == 422
    assert "anno-numero" in risposta.text


def test_due_moduli_aperti_non_si_sovrascrivono(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    pagina = f"/fascicoli/{civile.id}"
    indirizzo = f"{pagina}/stato"
    sarti, irene = browser("sarti"), browser("irene")
    prima = {"stato": "in_studio", "versione": "1"}
    assert invia(irene, indirizzo, prima, pagina=pagina).status_code == 303
    # Il modulo di Elena Sarti era stato aperto alla versione 1.
    assert invia(sarti, indirizzo, prima, pagina=pagina).status_code == 409
