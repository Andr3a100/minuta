"""Lo stile degli avvocati, nell'applicazione (lezione 23)."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest
from aiuti import invia
from sqlalchemy import func, inspect, select

from app import manage
from app.archivio import carica_atto
from app.db import (
    AttoArchivio,
    Evento,
    ProfiloStile,
    UsoAI,
    Utente,
    make_engine,
)
from app.migrations import PASSI, migra
from app.stile import (
    StileRifiutato,
    calcola_profilo,
    conferma_profilo,
    decidi_formule,
    letto,
    profilo_di,
)
from minuta.archivio import leggi_indice
from minuta.leaks import fughe

ARCHIVIO = Path(__file__).resolve().parents[2] / "archivio"
INDICE = leggi_indice(ARCHIVIO / "indice.csv")


def utente(db, nome_utente: str) -> Utente:
    return db.scalar(select(Utente).where(Utente.nome_utente == nome_utente))


@pytest.fixture
def archivio(app, impostazioni):
    with app.state.session_factory() as db:
        sarti = utente(db, "sarti")
        for pdf in sorted((ARCHIVIO / "pdf").glob("*.pdf")):
            carica_atto(db, impostazioni, sarti, pdf, INDICE[pdf.stem])


def da_decidere(dati: dict) -> list[int]:
    return [
        n
        for n, f in enumerate(dati["formule"], start=1)
        if f["stato"] == "da decidere"
    ]


# [libro:prova-stile-app]
def test_il_profilo_si_conferma_solo_con_le_norme_decise(app, archivio):
    with app.state.session_factory() as db:
        sarti = utente(db, "sarti")
        dati = letto(calcola_profilo(db, sarti))
        aperte = da_decidere(dati)
        assert aperte
        with pytest.raises(StileRifiutato, match="Restano da decidere"):
            conferma_profilo(db, sarti)
        decidi_formule(db, sarti, aperte, "tolta")
        assert conferma_profilo(db, sarti).confermato_il is not None


def test_il_profilo_e_di_chi_l_ha_scritto(app, archivio):
    with app.state.session_factory() as db:
        calcola_profilo(db, utente(db, "sarti"))
        irene = utente(db, "irene")
        with pytest.raises(StileRifiutato, match="di un avvocato"):
            calcola_profilo(db, irene)
        with pytest.raises(StileRifiutato, match="ancora un profilo"):
            decidi_formule(db, utente(db, "dini"), [1], "tolta")
        assert profilo_di(db, irene, utente(db, "sarti")) is not None
        with pytest.raises(StileRifiutato, match="segreteria"):
            profilo_di(db, utente(db, "rosa"), utente(db, "sarti"))


# [/libro:prova-stile-app]


def test_nel_profilo_salvato_nessun_dato_riservato(app, archivio):
    riservati = json.loads((ARCHIVIO / "entita.json").read_text("utf-8"))
    nomi = {v for k, vs in riservati.items() if k != "_nota" for v in vs}
    nomi.discard("Studio Meridiana")
    with app.state.session_factory() as db:
        for avvocato in ("sarti", "dini"):
            profilo = calcola_profilo(db, utente(db, avvocato))
            assert fughe(profilo.contenuto, sorted(nomi)) == []


def test_l_indice_e_lo_studio_nascondono_cio_che_le_regole_non_vedono(app):
    # Senza forma societaria né titolo, i nomi li nascondono soltanto
    # l'indice dello studio e l'elenco delle sue persone.
    frase = "Supermercati Lanza non ha pagato, e Marco Dini lo ha scritto."
    with app.state.session_factory() as db:
        dini = utente(db, "dini")
        for n in (1, 2):
            db.add(
                AttoArchivio(
                    nome=f"prova-{n}.pdf",
                    impronta=str(n) * 64,
                    tipo="ricorso decreto ingiuntivo",
                    autore_id=dini.id,
                    pagine=json.dumps([f"Atto {n}. {frase} Fine {n}."]),
                    persone=json.dumps(["Supermercati Lanza S.p.A."]),
                    nascosti=0,
                    caricato_da_id=dini.id,
                )
            )
        db.commit()
        profilo = calcola_profilo(db, dini)
    assert fughe(profilo.contenuto, ["Lanza", "Marco Dini", "Dini"]) == []
    assert "[SOGGETTO] non ha pagato" in profilo.contenuto


def test_contare_non_chiede_niente_a_nessuno(app, archivio):
    with app.state.session_factory() as db:
        calcola_profilo(db, utente(db, "sarti"))
        voci = db.scalar(select(func.count()).select_from(UsoAI))
        righe = db.scalar(
            select(func.count())
            .select_from(Evento)
            .where(Evento.azione == "stile")
        )
    assert (voci, righe) == (0, 1)


def test_senza_atti_non_c_e_profilo(app):
    with app.state.session_factory() as db:
        with pytest.raises(StileRifiutato, match="almeno due atti"):
            calcola_profilo(db, utente(db, "righi"))


def test_cambiare_una_formula_toglie_la_conferma(app, archivio):
    with app.state.session_factory() as db:
        sarti = utente(db, "sarti")
        dati = letto(calcola_profilo(db, sarti))
        decidi_formule(db, sarti, da_decidere(dati), "stile")
        conferma_profilo(db, sarti)
        decidi_formule(db, sarti, [1], "tolta")
        profilo = db.scalar(select(ProfiloStile))
        assert profilo.confermato_il is None
        with pytest.raises(StileRifiutato, match="formula 99"):
            decidi_formule(db, sarti, [99], "tolta")


def test_la_pagina_dello_stile(app, browser, archivio):
    sarti = browser("sarti")
    assert invia(sarti, "/stile", {"azione": "calcola"}).status_code == 303
    pagina = sarti.get("/stile").text
    assert "TRIBUNALE ORDINARIO DI MODENA" in pagina
    assert "da decidere" in pagina
    rifiutata = invia(sarti, "/stile", {"azione": "conferma"})
    assert rifiutata.status_code == 409
    assert browser("rosa").get("/stile").status_code == 404


def test_il_comando_mostra_le_norme_da_decidere(app, archivio, capsys):
    with app.state.session_factory() as db:
        manage.stile_dalla_riga(db, Namespace(di=None, da="sarti"))
    uscita = capsys.readouterr().out
    assert uscita.startswith("Lo stile di Elena Sarti, da 5 atti:")
    assert "! una norma, manca nell'atto 02: da decidere" in uscita
    assert "Il profilo è un conto: non è partito niente." in uscita


def test_la_migrazione_9_aggiunge_i_profili(impostazioni):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI.update({n: tutti[n] for n in range(1, 9)})  # la versione 0.8
        migra(engine)
        PASSI[9] = tutti[9]  # arriva la versione 0.9
        assert migra(engine) == [9]
        with engine.connect() as conn:
            assert inspect(conn).has_table("profili")
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
