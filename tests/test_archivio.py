import csv

import pytest

from minuta import archive
from percorsi import RADICE

ATTESI = list(csv.DictReader(open(RADICE / "archivio/indice.csv", encoding="utf-8"), delimiter=";"))


@pytest.mark.parametrize("atteso", ATTESI, ids=[a["id"] for a in ATTESI])
def test_metadati_letti_dal_pdf(atti, atteso):
    atto = atti[atteso["file"]]
    assert atto.data == atteso["data"]
    assert atto.autore == atteso["autore"]
    assert atto.tipo == atteso["tipo"]
    assert atto.giudice == (atteso["giudice"] or None)
    assert atto.valore == float(atteso["valore"])


def test_legature_e_a_capo_normalizzati():
    assert archive.normalizza("Oﬃcine Mecca-\nniche") == "Officine Meccaniche"


@pytest.mark.parametrize("file", ["01-2019-sarti-imballaggi-bassi", "03-2021-dini-officine-righi"])
def test_sezioni_nei_due_stili(atti, file):
    ruoli = [ruolo for ruolo, _ in atti[file].sezioni]
    for ruolo in ("fatti", "diritto", "conclusioni", "documenti", "firma"):
        assert ruolo in ruoli
