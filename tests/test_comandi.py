import json

from minuta.__main__ import main
from minuta.leaks import fughe
from conftest import RADICE


def test_gli_esempi_per_l_addestramento_sono_pseudonimizzati(oracolo, capsys):
    assert main(["importa"]) == 0
    assert main(["dataset"]) == 0
    testo = (RADICE / "addestramento/esempi.jsonl").read_text("utf-8")
    righe = [json.loads(r) for r in testo.splitlines()]
    assert len(righe) == 9  # i ricorsi dell'archivio, senza la diffida
    assert fughe(testo, {s for valori in oracolo.values() for s in valori}) == []
    assert "nello stile 1" in righe[0]["messages"][0]["content"]
