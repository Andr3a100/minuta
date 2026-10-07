"""La scheda dell'atto in arrivo, nell'applicazione (lezione 18).

Il decreto di Ristorazione Collinare va a capo dopo «Termocucine»: senza la
controparte in elenco la scheda non parte. Con la controparte, il modello
finto risponde con la sua scheda sbagliata apposta, e le prove seguono il
lavoro dello studio: la praticante toglie le righe, l'avvocato conferma.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiuti import con_fascicoli, invia
from sqlalchemy import func, insert, inspect, select

from app import documenti as app_documenti
from app.db import (
    Evento,
    Fascicolo,
    PersonaFascicolo,
    Scheda,
    UsoAI,
    Utente,
    make_engine,
)
from app.invio import aggiungi_persona
from app.migrations import PASSI, migra
from app.schede import (
    SchedaRifiutata,
    conferma_scheda,
    righe_di,
    togli_riga,
)
from minuta.model import ModelloFinto, Risposta

DECRETO = (
    Path(__file__).resolve().parents[2]
    / "documenti-di-prova"
    / "2026-071"
    / "decreto.pdf"
)
NOMI_VERI = ("Termocucine", "Secchia", "Ristorazione Collinare", "Sarti")


class ModelloCheRicorda(ModelloFinto):
    """Il modello finto delle prove, che in più tiene ciò che riceve."""

    def __init__(self, risposta: str | None = None):
        super().__init__()
        self.ricevuti: list[str] = []
        self.risposta = risposta

    def scrivi(self, sistema: str, richiesta: str) -> Risposta:
        self.ricevuti.append(sistema + "\n\n" + richiesta)
        if self.risposta is not None:
            return Risposta(self.risposta, "registratore", 100, 10)
        return super().scrivi(sistema, richiesta)


def quanti(app, tabella) -> int:
    with app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(tabella))


@pytest.fixture
def decreto(app, impostazioni):
    """Il fascicolo civile con il decreto caricato da Irene."""
    civile = con_fascicoli(app)["2026-071"]
    with app.state.session_factory() as db:
        irene = db.scalar(select(Utente).where(Utente.nome_utente == "irene"))
        documento, _ = app_documenti.carica(
            db,
            impostazioni,
            irene,
            db.get(Fascicolo, civile.id),
            DECRETO.name,
            DECRETO.read_bytes(),
        )
        indirizzo = f"/fascicoli/{civile.id}/documenti/{documento.id}/scheda"
    return civile, indirizzo


def controparte_in_elenco(app, fascicolo):
    with app.state.session_factory() as db:
        irene = db.scalar(select(Utente).where(Utente.nome_utente == "irene"))
        aggiungi_persona(
            db,
            irene,
            db.get(Fascicolo, fascicolo.id),
            "Termocucine Secchia S.r.l.",
            "controparte",
        )


def test_la_forma_societaria_dice_che_e_un_soggetto(app, decreto):
    civile, _ = decreto
    controparte_in_elenco(app, civile)
    with app.state.session_factory() as db:
        tipo = db.scalar(
            select(PersonaFascicolo.tipo).where(
                PersonaFascicolo.ruolo == "controparte"
            )
        )
    assert tipo == "SOGGETTO"


def test_senza_la_controparte_la_scheda_non_parte(app, browser, decreto):
    app.state.modello = registratore = ModelloCheRicorda()
    _civile, indirizzo = decreto
    risposta = invia(browser("irene"), indirizzo, {})
    assert risposta.status_code == 422
    assert "Nomi che non sono nell'elenco: Termocucine" in risposta.text
    assert registratore.ricevuti == []
    assert quanti(app, Scheda) == 0
    assert quanti(app, UsoAI) == 0


# [libro:prova-scheda-app]
def test_la_scheda_parte_pseudonimizzata_e_torna_controllata(
    app, browser, decreto
):
    app.state.modello = registratore = ModelloCheRicorda()
    civile, indirizzo = decreto
    controparte_in_elenco(app, civile)
    irene = browser("irene")
    assert invia(irene, indirizzo, {}).status_code == 303
    (inviato,) = registratore.ricevuti
    assert not any(nome in inviato for nome in NOMI_VERI)
    assert "SCHEDA:" in inviato and "PAGINA 1" in inviato
    pagina = irene.get(indirizzo).text
    assert "Controparte: Termocucine Secchia S.r.l." in pagina
    assert "importo 14.208,00 non è a pagina 1" in pagina
    with app.state.session_factory() as db:
        voce = db.scalar(select(UsoAI))
    assert voce.scopo == "scheda dell'atto in arrivo"


# [/libro:prova-scheda-app]


def test_la_praticante_toglie_l_avvocato_conferma(app, browser, decreto):
    app.state.modello = ModelloCheRicorda()
    civile, indirizzo = decreto
    controparte_in_elenco(app, civile)
    irene, sarti = browser("irene"), browser("sarti")
    invia(irene, indirizzo, {})
    # La praticante non conferma; l'avvocato non conferma righe segnalate.
    assert invia(irene, indirizzo + "/conferma", {}).status_code == 403
    rifiutata = invia(sarti, indirizzo + "/conferma", {})
    assert rifiutata.status_code == 409
    assert "Restano righe segnalate: 1, 2." in rifiutata.text
    # Tolte le due segnalate e la data della notificazione sbagliata, sì.
    for riga in (1, 2, 4):
        risposta = invia(irene, indirizzo + "/togli", {"riga": riga})
        assert risposta.status_code == 303
    assert invia(irene, indirizzo + "/togli", {"riga": 4}).status_code == 409
    assert invia(sarti, indirizzo + "/conferma", {}).status_code == 303
    pagina = sarti.get(indirizzo).text
    assert "Confermata da Elena Sarti" in pagina
    assert invia(sarti, indirizzo + "/togli", {"riga": 3}).status_code == 409
    with app.state.session_factory() as db:
        azioni = [e.azione for e in db.scalars(select(Evento))]
    assert azioni[-5:] == [
        "scheda",
        "riga tolta",
        "riga tolta",
        "riga tolta",
        "scheda confermata",
    ]


def test_la_segreteria_vede_la_scheda_ma_non_la_prepara(app, browser, decreto):
    app.state.modello = ModelloCheRicorda()
    civile, indirizzo = decreto
    controparte_in_elenco(app, civile)
    invia(browser("irene"), indirizzo, {})
    rosa = browser("rosa")
    assert rosa.get(indirizzo).status_code == 200
    assert invia(rosa, indirizzo, {}).status_code == 403
    assert invia(rosa, indirizzo + "/togli", {"riga": 1}).status_code == 403
    # Chi non lavora al fascicolo non lo vede nemmeno.
    assert browser("righi").get(indirizzo).status_code == 404


def test_una_risposta_illeggibile_resta_nel_registro(app, browser, decreto):
    app.state.modello = ModelloCheRicorda("Non posso preparare la scheda.")
    civile, indirizzo = decreto
    controparte_in_elenco(app, civile)
    risposta = invia(browser("irene"), indirizzo, {})
    assert risposta.status_code == 502
    assert "non è una scheda" in risposta.text
    assert quanti(app, UsoAI) == 1  # la richiesta è partita
    assert quanti(app, Scheda) == 0


def test_le_regole_valgono_anche_senza_il_browser(app, browser, decreto):
    # La riga di comando chiama le stesse funzioni: le regole stanno lì.
    app.state.modello = ModelloCheRicorda()
    civile, indirizzo = decreto
    controparte_in_elenco(app, civile)
    invia(browser("irene"), indirizzo, {})
    with app.state.session_factory() as db:
        fascicolo = db.get(Fascicolo, civile.id)
        scheda = db.scalar(select(Scheda))
        utenti = {u.nome_utente: u for u in db.scalars(select(Utente))}
        with pytest.raises(SchedaRifiutata, match="segreteria"):
            togli_riga(db, utenti["rosa"], fascicolo, scheda, 1)
        with pytest.raises(SchedaRifiutata, match="Solo un avvocato"):
            conferma_scheda(db, utenti["irene"], fascicolo, scheda)
        with pytest.raises(SchedaRifiutata, match="non ha una riga 9"):
            togli_riga(db, utenti["irene"], fascicolo, scheda, 9)


def test_un_segnaposto_inventato_dal_modello_si_segnala(app, browser, decreto):
    app.state.modello = ModelloCheRicorda(
        '{"righe": [{"voce": "parti", "pagina": 1, '
        '"testo": "Garante: [PERSONA_9]"}]}'
    )
    civile, indirizzo = decreto
    controparte_in_elenco(app, civile)
    assert invia(browser("irene"), indirizzo, {}).status_code == 303
    with app.state.session_factory() as db:
        (riga,) = righe_di(db.scalar(select(Scheda)))
    assert riga.problemi == ["segnaposto che nessuno conosce: [PERSONA_9]"]


def test_la_migrazione_4_aggiunge_le_schede(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in (1, 2, 3)})  # la versione 0.3
        migra(engine)
        with engine.begin() as conn:
            assert not inspect(conn).has_table("schede")
        PASSI[4] = tutti[4]  # arriva la versione 0.4
        assert migra(engine) == [4]
        with engine.begin() as conn:
            assert inspect(conn).has_table("schede")
            conn.execute(
                insert(Utente.__table__).values(
                    id=1,
                    nome_utente="sarti",
                    nome="Elena Sarti",
                    hash_passphrase="x",
                    ruolo="avvocato",
                    attivo=True,
                    creato_il=Utente.__table__.c.creato_il.default.arg(None),
                )
            )
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
