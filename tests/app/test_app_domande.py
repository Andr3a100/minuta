"""Le domande sul fascicolo, nell'applicazione (lezione 21)."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiuti import con_fascicoli, invia
from sqlalchemy import func, inspect, select

from app import documenti as app_documenti
from app.db import Fascicolo, RispostaFascicolo, UsoAI, Utente, make_engine
from app.invio import aggiungi_persona
from app.migrations import PASSI, migra
from app.registro import RichiestaNonAmmessa
from app.risposte import domanda_sul_fascicolo
from minuta.model import ModelloFinto, Risposta

AVVISO = (
    Path(__file__).resolve().parents[2]
    / "documenti-di-prova"
    / "2026-073"
    / "avviso-415-bis.pdf.p7m"
)
NOMI_VERI = ("Alessandro Riva", "Marco Bellini", "Stefano Valli", "Bellini")


class ModelloCheRicorda(ModelloFinto):
    def __init__(self, risposta: str | None = None):
        super().__init__()
        self.ricevuti: list[str] = []
        self.risposta = risposta

    def scrivi(self, sistema, richiesta):
        self.ricevuti.append(richiesta)
        if self.risposta is not None:
            return Risposta(self.risposta, "registratore", 100, 10)
        return super().scrivi(sistema, richiesta)


@pytest.fixture
def penale(app, impostazioni):
    fascicolo = con_fascicoli(app)["2026-073"]
    with app.state.session_factory() as db:
        valli = db.scalar(select(Utente).where(Utente.nome_utente == "valli"))
        dentro = db.get(Fascicolo, fascicolo.id)
        app_documenti.carica(
            db, impostazioni, valli, dentro, AVVISO.name, AVVISO.read_bytes()
        )
        aggiungi_persona(db, valli, dentro, "Marco Bellini", "persona offesa")
    return fascicolo


def quante(app, tabella):
    with app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(tabella))


# [libro:prova-domanda-app]
def test_partono_solo_i_passi_scelti_e_le_citazioni_si_controllano(
    app, browser, penale
):
    app.state.modello = registratore = ModelloCheRicorda()
    valli = browser("valli")
    indirizzo = f"/fascicoli/{penale.id}/domande"
    risposta = invia(
        valli, indirizzo, {"domanda": "Quali facoltà ha l'indagato?"}
    )
    assert risposta.status_code == 303
    (inviato,) = registratore.ricevuti
    assert not any(nome in inviato for nome in NOMI_VERI)
    assert "DOCUMENTO: avviso-415-bis.pdf.p7m · PAGINA 1" in inviato
    pagina = valli.get(indirizzo).text
    assert "PROCURA DELLA REPUBBLICA PRESSO IL TRIBUNALE DI MODENA" in pagina
    assert "la citazione non è a pagina 1" in pagina
    assert quante(app, UsoAI) == 1


def test_senza_passi_non_parte_niente(app, browser, penale):
    app.state.modello = registratore = ModelloCheRicorda()
    valli = browser("valli")
    indirizzo = f"/fascicoli/{penale.id}/domande"
    invia(
        valli, indirizzo, {"domanda": "Che cosa dice il consulente tecnico?"}
    )
    assert registratore.ricevuti == []
    assert quante(app, UsoAI) == 0
    assert "nel fascicolo non c" in valli.get(indirizzo).text


# [/libro:prova-domanda-app]


def test_la_citazione_con_i_segnaposto_si_controlla_con_i_nomi(
    app, browser, penale
):
    app.state.modello = ModelloCheRicorda(
        '{"frasi": [{"testo": "È indagato.", '
        '"documento": "avviso-415-bis.pdf.p7m", '
        '"pagina": 1, "citazione": "[PERSONA_1], legale rappresentante di '
        '[SOGGETTO_1], indagato"}]}'
    )
    invia(
        browser("valli"),
        f"/fascicoli/{penale.id}/domande",
        {"domanda": "Chi è l'indagato?"},
    )
    with app.state.session_factory() as db:
        frasi = __import__("json").loads(
            db.scalar(select(RispostaFascicolo)).frasi
        )
    assert frasi[0]["citazione"].startswith(
        "Alessandro Riva, legale rappresentante"
    )
    assert frasi[0]["problemi"] == []


def test_un_nome_fuori_elenco_nei_passi_blocca_la_domanda(
    app, browser, impostazioni
):
    # Nel fascicolo civile la controparte non è in elenco: il decreto va a
    # capo dopo «Termocucine» (lezione 18), e la domanda non parte.
    app.state.modello = registratore = ModelloCheRicorda()
    civile = con_fascicoli(app)["2026-071"]
    decreto = AVVISO.parents[1] / "2026-071" / "decreto.pdf"
    with app.state.session_factory() as db:
        irene = db.scalar(select(Utente).where(Utente.nome_utente == "irene"))
        app_documenti.carica(
            db,
            impostazioni,
            irene,
            db.get(Fascicolo, civile.id),
            decreto.name,
            decreto.read_bytes(),
        )
    risposta = invia(
        browser("irene"),
        f"/fascicoli/{civile.id}/domande",
        {"domanda": "Che cosa ingiunge il decreto?"},
    )
    assert risposta.status_code == 422
    assert "Termocucine" in risposta.text
    assert registratore.ricevuti == []


def test_la_segreteria_non_fa_domande_al_modello(app, browser, penale):
    app.state.modello = ModelloCheRicorda()
    indirizzo = f"/fascicoli/{penale.id}/domande"
    assert (
        invia(
            browser("rosa"), indirizzo, {"domanda": "Quali facoltà?"}
        ).status_code
        == 403
    )
    with app.state.session_factory() as db:
        rosa = db.scalar(select(Utente).where(Utente.nome_utente == "rosa"))
        with pytest.raises(RichiestaNonAmmessa):
            domanda_sul_fascicolo(
                db,
                rosa,
                db.get(Fascicolo, penale.id),
                "Che cosa dice il consulente?",
                ModelloFinto(),
            )


def test_una_risposta_illeggibile_resta_nel_registro(app, browser, penale):
    app.state.modello = ModelloCheRicorda("Non posso rispondere.")
    risposta = invia(
        browser("valli"),
        f"/fascicoli/{penale.id}/domande",
        {"domanda": "Quali facoltà ha l'indagato?"},
    )
    assert risposta.status_code == 502
    assert quante(app, UsoAI) == 1
    assert quante(app, RispostaFascicolo) == 0


def test_la_migrazione_7_aggiunge_le_risposte(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in range(1, 7)})  # la versione 0.6
        migra(engine)
        PASSI[7] = tutti[7]  # arriva la versione 0.7
        assert migra(engine) == [7]
        with engine.connect() as conn:
            assert inspect(conn).has_table("risposte")
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
