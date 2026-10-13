"""L'addestramento in locale (lezione 30): ciò che si prova senza
addestrare. L'addestramento vero gira sul server dello studio, nella prova
automatica."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from minuta import addestra
from minuta.addestra import InsiemeNonValido, dividi, perplessita, pezzi

RIGHE = [
    {"atto": "archivio-01", "testo": "uno"},
    {"atto": "archivio-02", "testo": "due"},
    {"atto": "archivio-05", "testo": "cinque"},
]


# [libro:prova-dividi]
def test_l_atto_tenuto_fuori_non_si_vede_mai():
    dentro, fuori = dividi(RIGHE, "archivio-05")
    assert dentro == ["uno", "due"] and fuori == ["cinque"]
    with pytest.raises(InsiemeNonValido, match="non c'è archivio-09"):
        dividi(RIGHE, "archivio-09")
    with pytest.raises(InsiemeNonValido, match="almeno due"):
        dividi(RIGHE[:1], "archivio-01")


# [/libro:prova-dividi]


def test_i_pezzi_e_l_ultimo_troppo_corto():
    assert pezzi(list(range(10)), 4) == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]
    assert pezzi(list(range(17)), 8) == [list(range(8)), list(range(8, 17))]
    assert pezzi([1, 2], 4) == [[1, 2]]


def test_la_perplessita_pesa_i_token():
    assert perplessita([(1.0, 3), (2.0, 1)]) == pytest.approx(math.exp(1.25))
    assert perplessita([(0.0, 5)]) == 1.0


ESITO = {
    "quando": "2026-10-14T10:00:00+00:00",
    "modello": "Qwen/Qwen2.5-0.5B",
    "revisione": addestra.REVISIONE,
    "insieme": "dati/addestramento/sarti.jsonl",
    "impronta": "0" * 64,
    "atti": 5,
    "fuori": "archivio-10",
    "pezzi": 12,
    "passate": 3,
    "addestrabili": 540672,
    "totali": 494573440,
    "perplessita": {"addestramento": [10.0, 4.0], "fuori": [11.0, 9.5]},
    "adattatore": "dati/modelli/sarti",
    "byte_adattatore": 2_200_000,
}


def test_il_resoconto():
    righe = addestra.resoconto(ESITO)
    assert (
        righe[2] == "Addestramento: 4 atti, 12 pezzi da 256 token, 3 passate."
    )
    assert righe[3] == "L'adattatore: 540.672 numeri, lo 0.11% del modello."
    assert righe[5] == "  sugli atti dell'addestramento    10.0 →    4.0"
    assert righe[6] == "  sull'atto tenuto fuori           11.0 →    9.5"


def test_il_comando(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(addestra, "addestra", lambda *a: dict(ESITO))
    assert (
        addestra.main(
            ["sarti.jsonl", "--fuori", "archivio-10", "--verbale", "v.json"]
        )
        == 0
    )
    verbale = json.loads((tmp_path / "v.json").read_text("utf-8"))
    assert verbale["stampa"] == capsys.readouterr().out.rstrip("\n")

    def rifiuta(*_):
        raise InsiemeNonValido("Nell'insieme non c'è archivio-99.")

    monkeypatch.setattr(addestra, "addestra", rifiuta)
    assert addestra.main(["sarti.jsonl", "--fuori", "archivio-99"]) == 1
    assert "archivio-99" in capsys.readouterr().err


def test_il_confronto_su_un_altro_insieme(monkeypatch, tmp_path, capsys):
    chiamate = []

    def finto(insieme, fuori, cartella, confronto=None):
        chiamate.append(confronto)
        return dict(
            ESITO,
            confronto=f"{confronto[0].as_posix()}:{confronto[1]}",
            perplessita_confronto=[26.1, 20.0],
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(addestra, "addestra", finto)
    argomenti = ["dini.jsonl", "--fuori", "archivio-09"]
    assert (
        addestra.main([*argomenti, "--confronto", "a/sarti.jsonl:archivio-10"])
        == 0
    )
    assert chiamate == [(Path("a/sarti.jsonl"), "archivio-10")]
    righe = capsys.readouterr().out.splitlines()
    assert righe[7:9] == [
        "  su a/sarti.jsonl:archivio-10",
        "                                   26.1 →   20.0",
    ]
