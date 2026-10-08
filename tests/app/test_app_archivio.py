"""L'archivio dello studio, nell'applicazione (lezione 22)."""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import date
from pathlib import Path

import pytest
from aiuti import con_fascicoli, invia
from sqlalchemy import func, inspect, select

from app import manage
from app.archivio import ArchivioRifiutato, carica_atto, cerca_nell_archivio
from app.db import (
    AttoArchivio,
    Evento,
    RispostaFascicolo,
    Segnaposto,
    UsoAI,
    Utente,
    make_engine,
)
from app.migrations import PASSI, migra
from app.registro import RichiestaNonAmmessa
from app.risposte import (
    NESSUN_ATTO,
    domanda_all_archivio,
    noti_con_l_archivio,
)
from minuta.archivio import leggi_indice
from minuta.invio import prepara
from minuta.leaks import fughe
from minuta.model import ModelloFinto, Risposta

ARCHIVIO = Path(__file__).resolve().parents[2] / "archivio"
INDICE = leggi_indice(ARCHIVIO / "indice.csv")
# I dati di ogni atto che non devono uscire. Il nome dello studio no: è il
# cliente del fornitore, e il fornitore lo conosce già.
RISERVATI = {
    atto: [v for v in valori if v != "Studio Meridiana"]
    for atto, valori in json.loads(
        (ARCHIVIO / "entita.json").read_text("utf-8")
    ).items()
    if not atto.startswith("_")
}


class ModelloCheRicorda(ModelloFinto):
    def __init__(self, risposta=None):
        super().__init__()
        self.ricevuti: list[str] = []
        self.risposta = risposta  # un testo, o una funzione della richiesta

    def scrivi(self, sistema, richiesta):
        self.ricevuti.append(richiesta)
        if self.risposta is None:
            return super().scrivi(sistema, richiesta)
        testo = (
            self.risposta(richiesta)
            if callable(self.risposta)
            else self.risposta
        )
        return Risposta(testo, "registratore", 100, 10)


def utente(db, nome_utente: str) -> Utente:
    return db.scalar(select(Utente).where(Utente.nome_utente == nome_utente))


@pytest.fixture
def civile(app, impostazioni):
    """Il fascicolo di Ristorazione Collinare, con l'archivio caricato."""
    fascicolo = con_fascicoli(app)["2026-071"]
    with app.state.session_factory() as db:
        sarti = utente(db, "sarti")
        for pdf in sorted((ARCHIVIO / "pdf").glob("*.pdf")):
            carica_atto(db, impostazioni, sarti, pdf, INDICE[pdf.stem])
    return fascicolo


def quante(app, tabella):
    with app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(tabella))


def test_gli_atti_entrano_con_i_dati_letti_dall_atto(app, civile):
    with app.state.session_factory() as db:
        atti = list(db.scalars(select(AttoArchivio).order_by(AttoArchivio.id)))
        dini = utente(db, "dini")
        assert len(atti) == 10
        assert (atti[2].data, atti[2].autore_id) == (
            date(2021, 2, 22),
            dini.id,
        )
        assert atti[8].tipo == "diffida e messa in mora"
        assert json.loads(atti[0].persone) == INDICE[Path(atti[0].nome).stem]
        righe = db.scalar(
            select(func.count())
            .select_from(Evento)
            .where(Evento.azione == "archivio")
        )
        assert righe == 10


def test_carica_un_avvocato_e_solo_con_le_persone(app, impostazioni, civile):
    pdf = ARCHIVIO / "pdf" / "01-2019-sarti-imballaggi-bassi.pdf"
    with app.state.session_factory() as db:
        with pytest.raises(ArchivioRifiutato, match="lo carica un avvocato"):
            carica_atto(db, impostazioni, utente(db, "irene"), pdf, ["X"])
        with pytest.raises(ArchivioRifiutato, match="manca nell'indice"):
            carica_atto(db, impostazioni, utente(db, "sarti"), pdf, None)
        with pytest.raises(ArchivioRifiutato, match="è già nell'archivio"):
            carica_atto(db, impostazioni, utente(db, "sarti"), pdf, ["X"])


def test_cercare_non_manda_niente(app, civile):
    app.state.modello = registratore = ModelloCheRicorda()
    with app.state.session_factory() as db:
        trovati = cerca_nell_archivio(
            db,
            utente(db, "irene"),
            "interessi moratori",
            autore="dini",
            al=date(2023, 12, 31),
        )
    assert [t.atto.numero for t in trovati] == [3, 4, 6]
    assert registratore.ricevuti == [] and quante(app, UsoAI) == 0


# [libro:prova-archivio-app]
def test_dall_archivio_i_nomi_partono_e_restano_segnaposto(
    app, browser, civile
):
    app.state.modello = registratore = ModelloCheRicorda()
    domanda = {"domanda": "La resistente ha contestato la fornitura?"}
    indirizzo = f"/fascicoli/{civile.id}/domande"
    invia(browser("irene"), indirizzo, {**domanda, "fonte": "archivio"})
    (inviato,) = registratore.ricevuti
    assert "DOCUMENTO: archivio-01 · PAGINA 1" in inviato
    assert "ricorso.pdf" not in inviato  # il fascicolo non si mescola
    assert fughe(inviato, RISERVATI["01-2019-sarti-imballaggi-bassi"]) == []
    with app.state.session_factory() as db:
        risposta = db.scalar(select(RispostaFascicolo))
        salvati = {s.valore for s in db.scalars(select(Segnaposto))}
    assert risposta.fonte == "archivio"
    assert not any("lanza" in v.casefold() for v in salvati)


# [/libro:prova-archivio-app]


def test_ogni_atto_dell_archivio_parte_senza_i_suoi_riservati(app, civile):
    with app.state.session_factory() as db:
        for atto in db.scalars(select(AttoArchivio)):
            noti = noti_con_l_archivio(db, civile, [atto])
            preparato = prepara("\n\n".join(json.loads(atto.pagine)), noti)
            assert not preparato.bloccato, atto.nome
            riservati = RISERVATI[Path(atto.nome).stem]
            assert fughe(preparato.testo, riservati) == [], atto.nome


def test_l_indice_e_lo_studio_coprono_cio_che_le_regole_non_vedono(
    app, civile
):
    # Senza forma societaria né titolo, nessuna regola riconosce un nome:
    # lo nascondono l'indice dello studio e l'elenco delle sue persone.
    testo = "Supermercati Lanza non ha pagato; Marco Dini ha firmato."
    with app.state.session_factory() as db:
        atto = db.get(AttoArchivio, 1)
        preparato = prepara(testo, noti_con_l_archivio(db, civile, [atto]))
    assert fughe(preparato.testo, ["Lanza", "Marco Dini", "Dini"]) == []


def test_le_citazioni_si_controllano_sulle_pagine_partite(app, civile):
    def cita_la_controparte(richiesta):
        riga = next(
            r for r in richiesta.splitlines() if r.startswith("contro")
        )
        segno = riga.split()[1]
        frasi = [
            {
                "testo": f"La controparte era {segno}.",
                "documento": "archivio-01",
                "pagina": 1,
                "citazione": riga,
            },
            {
                "testo": "Con il nome vero.",
                "documento": "archivio-01",
                "pagina": 1,
                "citazione": "contro: SUPERMERCATI LANZA S.P.A.",
            },
        ]
        return json.dumps({"frasi": frasi})

    modello = ModelloCheRicorda(cita_la_controparte)
    with app.state.session_factory() as db:
        esito = domanda_all_archivio(
            db,
            utente(db, "irene"),
            civile,
            "Chi era la controparte della fornitura di imballaggi?",
            modello,
        )
    prima, seconda = esito.frasi
    assert prima.testo.startswith("La controparte era [SOGGETTO_")
    assert prima.problemi == []
    fuori = "la citazione non è a pagina 1 di archivio-01"
    assert seconda.problemi == [fuori]


def test_senza_pagine_dall_archivio_non_parte_niente(app, civile):
    modello = ModelloCheRicorda()
    with app.state.session_factory() as db:
        esito = domanda_all_archivio(
            db,
            utente(db, "irene"),
            civile,
            "Che cosa dice la perizia sul soppalco?",
            modello,
        )
    assert (esito.manca, esito.fonte) == (NESSUN_ATTO, "archivio")
    assert modello.ricevuti == [] and quante(app, UsoAI) == 0


def test_la_segreteria_non_consulta_l_archivio(app, browser, civile):
    with app.state.session_factory() as db:
        rosa = utente(db, "rosa")
        with pytest.raises(ArchivioRifiutato):
            cerca_nell_archivio(db, rosa, "interessi")
        with pytest.raises(RichiestaNonAmmessa):
            domanda_all_archivio(
                db, rosa, civile, "Interessi?", ModelloCheRicorda()
            )
    assert browser("rosa").get("/archivio").status_code == 404
    pagina = browser("irene").get("/archivio").text
    assert "Atti nell'archivio: 10" in pagina


def test_la_pagina_dell_archivio_cerca_con_i_filtri(app, browser, civile):
    pagina = browser("irene").get(
        "/archivio",
        params={"parole": "provvisoria esecuzione", "dal": "2022-01-01"},
    )
    assert "Atto 05" in pagina.text and "Atto 10" in pagina.text
    assert "Atto 01" not in pagina.text  # è del 2019
    assert "pagina 1: esecu, provv" in pagina.text


def test_il_comando_cerca_dice_perche(app, civile, capsys):
    with app.state.session_factory() as db:
        manage.cerca_dalla_riga(
            db,
            Namespace(
                parole="provvisoria esecuzione",
                tipo="ricorso",
                autore=None,
                dal=None,
                al=None,
                da="irene",
            ),
        )
    uscita = capsys.readouterr().out
    assert uscita.startswith("Atti con le parole cercate: 5 su 10.")
    assert "    pagina 1: provv · pagina 2: esecu" in uscita
    assert "non è partito niente" in uscita


def test_la_migrazione_8_aggiunge_l_archivio_e_la_fonte(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in range(1, 8)})  # la versione 0.7
        migra(engine)
        PASSI[8] = tutti[8]  # arriva la versione 0.8
        assert migra(engine) == [8]
        with engine.connect() as conn:
            assert inspect(conn).has_table("archivio")
            colonne = {
                c["name"] for c in inspect(conn).get_columns("risposte")
            }
        assert "fonte" in colonne
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
