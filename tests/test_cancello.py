"""Il cancello di una modifica (lezione 29)."""

from __future__ import annotations

import json

from minuta import cancello
from minuta.cancello import Esame, riferimento_peggiorato, risposte_cambiate

CASI = [
    {"id": "a", "domanda": "uno?", "attesi": ["x.pdf"], "nota": "vecchia"},
    {"id": "b", "termine": "t", "partenza": "2026-01-01", "attesa": "x"},
    {"id": "c", "testo": "art. 1", "attese": []},
]


# [libro:prova-cancello]
def test_una_modifica_non_cambia_la_misura():
    dopo = json.loads(json.dumps(CASI))
    dopo[0]["nota"] = "nuova"  # la nota si può riscrivere
    assert risposte_cambiate(CASI, dopo) == []
    dopo[0]["attesi"] = ["y.pdf"]  # la risposta no
    dopo[1]["partenza"] = "2026-02-01"  # e nemmeno la domanda
    del dopo[2]
    assert risposte_cambiate(CASI, dopo) == [
        "a: attesi",
        "b: partenza",
        "c: tolto",
    ]
    assert riferimento_peggiorato(
        {"a": True, "b": False, "c": True}, {"a": False, "b": True}
    ) == ["a", "c"]


# [/libro:prova-cancello]


def test_quando_il_cancello_e_aperto():
    aperto = Esame("v1", [], [], [], [], [], ["prove: assert x"], ["req"])
    assert aperto.passa  # asserzioni e dipendenze si leggono, non fermano
    for campo in ("risposte_cambiate", "riferimento_peggiorato", "peggiorati"):
        chiuso = Esame("v1", [], [], [], [], [])
        setattr(chiuso, campo, ["x"])
        assert not chiuso.passa
    assert cancello.resoconto(aperto)[-1].startswith("Il cancello è aperto")


def test_l_esame_confronta_con_la_versione_di_partenza(monkeypatch):
    casi = json.loads(cancello.valutazione.CASI.read_text("utf-8"))
    vecchi = {**casi, "casi": casi["casi"][:-1]}  # un caso nuovo, poi
    riferimento = json.loads(
        cancello.valutazione.RIFERIMENTO.read_text("utf-8")
    )
    risposte = {
        (
            "diff",
            "--name-only",
            "v9",
            "HEAD",
        ): "minuta/x.py\nrequirements.txt\n",
        ("show", "v9:valutazione/casi.json"): json.dumps(vecchi),
        ("show", "v9:valutazione/riferimento.json"): json.dumps(
            {**riferimento, "passi-forno": False}
        ),
        ("diff", "-U0", "v9", "HEAD", "--", "tests"): (
            "--- a/tests/test_x.py\n-    assert 1 == 1\n+    assert 2 == 2\n"
        ),
    }
    monkeypatch.setattr(cancello, "_git", lambda *a: risposte[a])
    esame = cancello.esamina("v9")
    assert esame.passa
    assert esame.migliorati == ["passi-forno"]
    assert esame.dipendenze == ["requirements.txt"]
    assert esame.asserzioni_tolte == ["tests/test_x.py: assert 1 == 1"]


def test_la_strada_corta_non_passa(monkeypatch, capsys):
    """Lo script della lezione: il caso del forno fatto passare cambiando la
    sua risposta. La versione di partenza è quella di oggi, con il forno
    ancora da far passare."""
    import importlib.util

    from percorsi import RADICE

    riferimento = json.loads(
        cancello.valutazione.RIFERIMENTO.read_text("utf-8")
    )
    base = {
        "valutazione/casi.json": cancello.valutazione.CASI.read_text("utf-8"),
        "valutazione/riferimento.json": json.dumps(
            {**riferimento, "passi-forno": False}
        ),
    }
    monkeypatch.setattr(
        cancello, "alla_base", lambda _v, percorso: base[percorso]
    )
    spec = importlib.util.spec_from_file_location(
        "modifica_che_bara", RADICE / "percorso" / "modifica_che_bara.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    casi_prima = cancello.valutazione.CASI
    assert script.main() == 1
    assert cancello.valutazione.CASI == casi_prima  # i percorsi tornano
    uscita = capsys.readouterr().out
    assert "  casi superati: 41 su 41\n" in uscita  # la suite, da sola, sì
    assert "Casi cambiati: 1.\n  passi-forno: attesi\n" in uscita
    assert uscita.endswith("la modifica non entra in uso.\n")
