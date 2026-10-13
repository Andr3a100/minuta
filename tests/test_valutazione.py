"""La suite di valutazione (lezione 27): casi con la risposta nota, e un
riferimento che nessuna modifica può peggiorare."""

from __future__ import annotations

import importlib.util
import json

import pytest
from percorsi import RADICE

from app import manage
from minuta import archivio, domande, valutazione
from minuta.valutazione import Esito, confronta, esegui


# [libro:prova-suite]
def test_nessuna_modifica_peggiora_la_suite():
    """Il cancello: gira a ogni modifica, nella prova automatica."""
    esiti = esegui(valutazione.carica_casi())
    peggiorati, _ = confronta(esiti, valutazione.carica_riferimento())
    assert [e.id for e in peggiorati] == []


# [/libro:prova-suite]


def test_il_riferimento_ha_tutti_i_casi():
    casi = {c["id"] for c in valutazione.carica_casi()}
    assert set(valutazione.carica_riferimento()) == casi
    assert len(casi) == len(valutazione.carica_casi())  # niente doppioni


def test_peggiorati_migliorati_e_casi_nuovi():
    esiti = [
        Esito("passava", "passi", False, ""),
        Esito("non-passava", "passi", True, ""),
        Esito("nuovo-che-fallisce", "passi", False, ""),
        Esito("nuovo-che-passa", "passi", True, ""),
        Esito("fallisce-ancora", "passi", False, ""),
    ]
    riferimento = {
        "passava": True,
        "non-passava": False,
        "fallisce-ancora": False,
    }
    peggiorati, migliorati = confronta(esiti, riferimento)
    assert [e.id for e in peggiorati] == ["passava", "nuovo-che-fallisce"]
    assert [e.id for e in migliorati] == ["non-passava"]


def caso_di(id_: str) -> dict:
    return next(c for c in valutazione.carica_casi() if c["id"] == id_)


def test_non_parte_una_pagina_che_non_ne_parla():
    caso = caso_di("passi-contabile")
    assert esegui([caso])[0].superato
    assert not esegui([{**caso, "esclusi": ["promemoria.docx"]}])[0].superato
    assert not esegui([{**caso, "attesi": []}])[0].superato  # nessuna


@pytest.mark.parametrize(
    ("id_", "campo", "sbagliato"),
    [
        ("passi-notifica", "attesi", ["fattura-168.xml.p7m"]),
        ("archivio-01", "atteso", "09"),
        ("scadenza-agosto", "attesa", "2026-09-19"),
        ("scadenza-cartella-agosto", "attesa", "2026-09-08"),
        ("somme-100", "attese", [True]),
        ("citazioni-comma", "attese", ["c.p.c. art. 641"]),
        ("scheda-avviso", "segnalate", ["importi"]),
    ],
)
def test_una_risposta_sbagliata_non_passa(id_, campo, sbagliato):
    caso = caso_di(id_)
    assert esegui([caso])[0].superato
    assert not esegui([{**caso, campo: sbagliato}])[0].superato


def test_le_radici_corte_non_entrano_in_uso(monkeypatch, capsys):
    monkeypatch.setattr(domande, "parole", domande.parole)
    monkeypatch.setattr(archivio, "parole", archivio.parole)
    spec = importlib.util.spec_from_file_location(
        "radici_corte", RADICE / "percorso" / "radici_corte.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert script.main() == 1
    # la ricerca nell'archivio usa la stessa funzione: vale anche lì
    assert archivio.parole is domande.parole is script.parole_corte
    uscita = capsys.readouterr().out
    assert "Rispetto al riferimento, migliorati: 1.\n  passi-forno" in uscita
    assert "  passi-consulente-civile\nLa modifica non entra in uso." in uscita


def test_il_comando_e_il_riferimento(monkeypatch, tmp_path, capsys):
    riferimento = tmp_path / "riferimento.json"
    riferimento.write_text(json.dumps({"passi-forno": True}), "utf-8")
    monkeypatch.setattr(valutazione, "RIFERIMENTO", riferimento)
    assert manage.valuta() == 1  # il forno «passava»: ora è peggiorato
    assert "La modifica non entra in uso." in capsys.readouterr().out
    assert manage.valuta(accetta=True) == 0
    assert "Riferimento aggiornato: 40 casi su 41 passano." in (
        capsys.readouterr().out
    )
    assert json.loads(riferimento.read_text("utf-8"))["passi-forno"] is False
    assert manage.valuta() == 0
