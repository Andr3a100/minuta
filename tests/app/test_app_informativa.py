"""L'informativa sull'IA al cliente e il segno dei testi generati
(lezione 34)."""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

import pytest
from aiuti import con_fascicoli, invia
from sqlalchemy import func, inspect, select

from app import documenti as app_documenti
from app import informativa, manage
from app.db import Evento, Fascicolo, UsoAI, Utente, adesso, make_engine
from app.informativa import (
    InformativaMancante,
    ModelloConInformativa,
    ModelloDelFascicolo,
    impronta_attuale,
    per_il_fascicolo,
    registra_consegna,
)
from app.invio import aggiungi_persona
from app.migrations import PASSI, migra
from app.segno import PAROLA, leggi_segno, segna
from minuta import word
from minuta.model import ModelloFinto

RADICE = Path(__file__).resolve().parents[2]
AVVISO = RADICE / "documenti-di-prova" / "2026-073" / "avviso-415-bis.pdf.p7m"


class Registratore(ModelloFinto):
    def __init__(self):
        super().__init__()
        self.ricevuti: list[str] = []

    def scrivi(self, sistema, richiesta):
        self.ricevuti.append(richiesta)
        return super().scrivi(sistema, richiesta)


def utente(db, nome):
    return db.scalar(select(Utente).where(Utente.nome_utente == nome))


@pytest.fixture
def penale(app, impostazioni):
    """Il fascicolo di Riva, con l'avviso e la persona offesa in elenco;
    il modello dell'applicazione ha davanti il controllo dell'informativa."""
    fascicolo = con_fascicoli(app)["2026-073"]
    with app.state.session_factory() as db:
        valli = utente(db, "valli")
        dentro = db.get(Fascicolo, fascicolo.id)
        app_documenti.carica(
            db, impostazioni, valli, dentro, AVVISO.name, AVVISO.read_bytes()
        )
        aggiungi_persona(db, valli, dentro, "Marco Bellini", "persona offesa")
    app.state.registratore = Registratore()
    app.state.modello = ModelloConInformativa(
        app.state.registratore, impostazioni.database_url
    )
    return fascicolo


def consegna(app, fascicolo, chi="rosa", giorno=date(2026, 10, 1)):
    with app.state.session_factory() as db:
        registra_consegna(
            db, utente(db, chi), db.get(Fascicolo, fascicolo.id), giorno, "PEC"
        )


def quante(app):
    with app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(UsoAI))


def test_il_modello_dell_applicazione_ha_davanti_l_informativa(app):
    assert isinstance(app.state.modello, ModelloConInformativa)


def test_senza_consegna_nessuna_richiesta_parte_dal_browser(
    app, browser, penale
):
    valli = browser("valli")
    domande = f"/fascicoli/{penale.id}/domande"
    risposta = invia(valli, domande, {"domanda": "Quali facoltà ha?"})
    assert risposta.status_code == 409
    assert "non ha ricevuto l&#39;informativa" in risposta.text
    # La pagina della domanda su un documento è della lezione 17.
    risposta = invia(
        valli,
        f"/fascicoli/{penale.id}/documenti/1/domanda",
        {"domanda": "Quali facoltà ha?", "azione": "invia"},
    )
    assert risposta.status_code == 403
    bozze = f"/fascicoli/{penale.id}/bozze"
    assert invia(valli, bozze, {"tipo": "promemoria"}).status_code == 409
    assert app.state.registratore.ricevuti == []
    assert quante(app) == 0
    consegna(app, penale)
    risposta = invia(valli, domande, {"domanda": "Quali facoltà ha?"})
    assert risposta.status_code == 303
    assert len(app.state.registratore.ricevuti) == 1


def test_un_testo_cambiato_va_consegnato_di_nuovo(
    app, browser, penale, tmp_path, monkeypatch
):
    consegna(app, penale)
    nuovo = tmp_path / "informativa.md"
    nuovo.write_text(informativa.TESTO.read_text("utf-8") + "\nUna frase.\n")
    monkeypatch.setattr(informativa, "TESTO", nuovo)
    valli = browser("valli")
    domande = f"/fascicoli/{penale.id}/domande"
    risposta = invia(valli, domande, {"domanda": "Quali facoltà ha?"})
    assert risposta.status_code == 409
    assert "non è quella di oggi" in risposta.text
    assert "1° ottobre 2026" in risposta.text
    consegna(app, penale, giorno=adesso().date())
    assert invia(valli, domande, {"domanda": "Quali?"}).status_code == 303


def test_gli_a_capo_di_windows_non_cambiano_l_impronta(tmp_path):
    unix, windows = tmp_path / "u.md", tmp_path / "w.md"
    unix.write_bytes(b"riga uno\nriga due\n")
    windows.write_bytes(b"riga uno\r\nriga due\r\n")
    assert impronta_attuale(unix) == impronta_attuale(windows)
    altro = tmp_path / "a.md"
    altro.write_bytes(b"riga uno\nriga tre\n")
    assert impronta_attuale(unix) != impronta_attuale(altro)


def test_chi_registra_e_che_cosa(app, penale):
    with app.state.session_factory() as db:
        f = db.get(Fascicolo, penale.id)
        with pytest.raises(InformativaMancante, match="avvocato o la segr"):
            registra_consegna(
                db, utente(db, "irene"), f, date(2026, 10, 1), "a"
            )
        domani = adesso().date() + timedelta(days=1)
        with pytest.raises(InformativaMancante, match="futura"):
            registra_consegna(db, utente(db, "rosa"), f, domani, "PEC")
        with pytest.raises(InformativaMancante, match="come è stata"):
            registra_consegna(
                db, utente(db, "rosa"), f, date(2026, 10, 1), " "
            )
        registra_consegna(db, utente(db, "valli"), f, date(2026, 10, 1), "PEC")
        assert f.informativa_impronta == impronta_attuale()
        riga = db.scalar(select(Evento).where(Evento.azione == "informativa"))
        assert json.loads(riga.dettaglio)["consegnata_il"] == "2026-10-01"


def test_dal_terminale_e_senza_fascicolo(app, penale):
    registratore = Registratore()
    davanti = ModelloConInformativa(
        registratore, app.state.settings.database_url
    )
    with pytest.raises(InformativaMancante):
        ModelloDelFascicolo(davanti, penale.id).scrivi("s", "r")
    # Una richiesta senza fascicolo non porta i dati di un cliente.
    davanti.scrivi("s", "r")
    with per_il_fascicolo(None):
        davanti.scrivi("s", "r")
    assert len(registratore.ricevuti) == 2
    consegna(app, penale)
    ModelloDelFascicolo(davanti, penale.id).scrivi("s", "r")
    assert len(registratore.ricevuti) == 3


def test_il_segno_nelle_proprieta_del_file(tmp_path):
    percorso = word.scrivi("# Bozza\n\nUn paragrafo.", tmp_path / "b.docx")
    assert leggi_segno(percorso) == []
    segna(percorso, "gpt-6.1-sol")
    righe = leggi_segno(percorso)
    assert righe[0] == f"Parole chiave: {PAROLA}"
    assert "con il modello gpt-6.1-sol" in righe[2]
    assert "non è un atto" in righe[2]


def test_il_file_scaricato_dal_browser_porta_il_segno(app, browser, penale):
    consegna(app, penale)
    valli = browser("valli")
    bozze = f"/fascicoli/{penale.id}/bozze"
    assert invia(valli, bozze, {"tipo": "promemoria"}).status_code == 303
    risposta = valli.get(f"{bozze}/1/word")
    assert risposta.status_code == 200
    file = Path(app.state.settings.data_dir) / "scaricata.docx"
    file.write_bytes(risposta.content)
    assert leggi_segno(file)[0] == f"Parole chiave: {PAROLA}"


def test_la_migrazione_14_aggiunge_l_informativa(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in range(1, 14)})  # la 1.2.4
        migra(engine)
        PASSI[14] = tutti[14]
        assert migra(engine) == [14]
        with engine.connect() as conn:
            colonne = {
                c["name"] for c in inspect(conn).get_columns("fascicoli")
            }
        assert {"informativa_il", "informativa_impronta"} <= colonne
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()


def test_anche_dal_terminale(app, penale, capsys):
    domanda = Namespace(
        codice="2026-073",
        domanda="Quali facoltà ha l'indagato?",
        da="valli",
        archivio=False,
        tipo=None,
        autore=None,
        dal=None,
        al=None,
        verbale=None,
    )
    with app.state.session_factory() as db:
        with pytest.raises(InformativaMancante, match="2026-073"):
            manage.domanda_al_fascicolo(db, app.state.settings, domanda)
    consegna(app, penale)
    with app.state.session_factory() as db:
        assert (
            manage.domanda_al_fascicolo(db, app.state.settings, domanda) == 0
        )
