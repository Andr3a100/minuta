"""I documenti del fascicolo nell'applicazione (lezione 16): chi li carica,
chi li vede, la riga nel registro, l'originale, i comandi."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from aiuti import carica_file, con_fascicoli, gettone_da
from sqlalchemy import func, inspect, select

from app import documenti as app_documenti
from app import manage
from app.db import Documento, Evento, Fascicolo, Utente, make_engine
from app.migrations import PASSI, migra

PROVA = Path(__file__).resolve().parents[2] / "documenti-di-prova"
DECRETO = (PROVA / "2026-071" / "decreto.pdf").read_bytes()


def quanti(app, tabella) -> int:
    with app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(tabella))


def test_irene_carica_il_decreto_e_la_scheda_lo_mostra(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    irene = browser("irene")
    risposta = carica_file(irene, civile, "decreto.pdf", DECRETO)
    assert risposta.status_code == 303
    pagina = irene.get(risposta.headers["location"])
    assert "la somma di euro 14.280,00" in pagina.text
    scheda = irene.get(f"/fascicoli/{civile.id}")
    assert "documento caricato: decreto.pdf" in scheda.text
    originale = irene.get(risposta.headers["location"] + "/originale")
    assert originale.content == DECRETO
    assert originale.headers["content-disposition"].startswith("attachment;")


def test_chi_non_lavora_al_fascicolo_non_carica_e_non_vede(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    valli = browser("valli")
    assert (
        carica_file(valli, civile, "decreto.pdf", DECRETO).status_code == 404
    )
    assert quanti(app, Documento) == 0
    indirizzo = carica_file(
        browser("irene"), civile, "decreto.pdf", DECRETO
    ).headers["location"]
    assert valli.get(indirizzo).status_code == 404
    assert valli.get(indirizzo + "/originale").status_code == 404


def test_un_documento_si_apre_solo_dal_suo_fascicolo(app, browser):
    fascicoli = con_fascicoli(app)
    rosa = browser("rosa")  # ha aperto tutti e tre i fascicoli
    indirizzo = carica_file(
        rosa, fascicoli["2026-071"], "decreto.pdf", DECRETO
    ).headers["location"]
    numero = indirizzo.rsplit("/", 1)[1]
    tributario = fascicoli["2026-072"].id
    assert (
        rosa.get(f"/fascicoli/{tributario}/documenti/{numero}").status_code
        == 404
    )


def test_lo_stesso_documento_non_entra_due_volte(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    irene = browser("irene")
    carica_file(irene, civile, "decreto.pdf", DECRETO)
    doppio = carica_file(irene, civile, "copia.pdf", DECRETO)
    assert doppio.status_code == 422
    assert "È già nel fascicolo, come decreto.pdf." in doppio.text
    assert quanti(app, Documento) == 1


def test_il_documento_e_la_sua_riga_insieme_o_per_niente(
    app, browser, monkeypatch
):
    civile = con_fascicoli(app)["2026-071"]
    irene = browser("irene")  # entra prima del guasto: l'accesso scrive
    gettone = gettone_da(irene, "/fascicoli")
    righe = quanti(app, Evento)

    def guasto(*args, **kwargs):
        raise RuntimeError("guasto simulato mentre si scrive la riga")

    monkeypatch.setattr("app.documenti.registra_evento", guasto)
    with pytest.raises(RuntimeError, match="guasto simulato"):
        irene.post(
            f"/fascicoli/{civile.id}/documenti",
            data={"csrf_token": gettone},
            files={"file": ("decreto.pdf", DECRETO, "application/pdf")},
        )
    assert quanti(app, Documento) == 0
    assert quanti(app, Evento) == righe


def test_un_modulo_resta_piccolo_un_documento_no(app, browser):
    civile = con_fascicoli(app)["2026-071"]
    irene = browser("irene")
    grande = b"%PDF-1.7\n" + b"0" * 200_000  # 200 KB: un PDF, se pure rotto
    risposta = carica_file(irene, civile, "grande.pdf", grande)
    assert risposta.status_code == 303
    assert (
        "Il PDF è danneggiato" in irene.get(risposta.headers["location"]).text
    )
    gettone = gettone_da(irene, "/accesso")
    troppo = irene.post(
        "/accesso", data={"csrf_token": gettone, "nome_utente": "x" * 20_000}
    )
    assert troppo.status_code == 413


def test_il_comando_carica_segue_le_regole_del_browser(
    app, impostazioni, capsys
):
    con_fascicoli(app)
    with app.state.session_factory() as db:
        with pytest.raises(manage.CommandError, match="non lavora"):
            manage.fascicolo_e_utente(db, "2026-073", "irene")
        argomenti = SimpleNamespace(
            codice="2026-072",
            percorsi=[str(PROVA / "2026-072")],
            da="righi",
        )
        assert manage.carica_file(db, impostazioni, argomenti) == 0
        manage.stampa_testo(db, "2026-072", "cartella-scansione.pdf")
    uscita = capsys.readouterr().out
    assert "Fascicolo 2026-072, caricati da Paola Righi:" in uscita
    assert "cartella-scansione.pdf: PDF, 1 pagina, lettura ottica" in uscita
    assert "--- pagina 1, lettura ottica a 100 punti per pollice ---" in uscita
    assert "Diritti di notifica 5,68" in uscita
    assert quanti(app, Documento) == 2


def test_l_originale_resta_com_e_arrivato(app, impostazioni):
    civile = con_fascicoli(app)["2026-071"]
    with app.state.session_factory() as db:
        irene = db.scalar(select(Utente).where(Utente.nome_utente == "irene"))
        fascicolo = db.get(Fascicolo, civile.id)
        documento, _ = app_documenti.carica(
            db, impostazioni, irene, fascicolo, "../../decreto.pdf", DECRETO
        )
        assert documento.nome == "decreto.pdf"  # solo il nome, mai cartelle
        percorso = app_documenti.originale(impostazioni, documento)
    assert percorso.read_bytes() == DECRETO
    assert percorso.parent == Path(impostazioni.data_dir) / "documenti"


def test_la_migrazione_porta_un_database_della_0_1_alla_0_2(
    impostazioni, monkeypatch
):
    tutti = dict(PASSI)
    engine = make_engine(impostazioni.database_url)
    try:
        PASSI.clear()
        PASSI[1] = tutti[1]  # il codice della versione 0.1
        assert migra(engine) == [1]
        assert not inspect(engine).has_table("documenti")
        PASSI[2] = tutti[2]  # arriva la versione 0.2
        assert migra(engine) == [2]
        assert inspect(engine).has_table("documenti")
    finally:
        PASSI.clear()
        PASSI.update(tutti)
        engine.dispose()
