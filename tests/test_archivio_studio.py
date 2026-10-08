"""La ricerca nell'archivio dello studio (lezione 22): per parole, tipo,
autore e periodo, con le etichette che non portano i nomi dei file."""

from __future__ import annotations

import csv
import json
from datetime import date

import pytest
from percorsi import RADICE

from minuta import documenti
from minuta.archivio import (
    AttoLetto,
    cerca,
    dati_dell_atto,
    etichetta,
    filtra,
    leggi_indice,
    passi_dell_archivio,
    tipo_del_nome,
)

ARCHIVIO = RADICE / "archivio"
AVVOCATI = [
    {"id": "sarti", "nome": "Elena Sarti"},
    {"id": "dini", "nome": "Marco Dini"},
]
INDICE = list(
    csv.DictReader(
        open(ARCHIVIO / "indice.csv", encoding="utf-8"), delimiter=";"
    )
)


def atti() -> list[AttoLetto]:
    letti = []
    for n, pdf in enumerate(sorted((ARCHIVIO / "pdf").glob("*.pdf")), 1):
        dati = dati_dell_atto(pdf, AVVOCATI)
        pagine = documenti.leggi(pdf.name, pdf.read_bytes()).pagine
        letti.append(
            AttoLetto(
                n,
                dati["tipo"],
                dati["autore"],
                dati["data"],
                [p.testo for p in pagine],
            )
        )
    return letti


ATTI = atti()


@pytest.mark.parametrize("riga", INDICE, ids=[r["id"] for r in INDICE])
def test_i_dati_si_leggono_dall_atto(riga):
    atto = ATTI[int(riga["id"]) - 1]
    assert atto.data == date.fromisoformat(riga["data"])
    assert (atto.autore, atto.tipo) == (riga["autore"], riga["tipo"])


# [libro:prova-ricerca]
def test_tipo_autore_e_periodo():
    numeri = [a.numero for a in filtra(ATTI, tipo="ricorso", autore="dini")]
    assert numeri == [3, 4, 6, 8]
    dal_2024 = filtra(ATTI, dal=date(2024, 1, 1))
    assert [a.numero for a in dal_2024] == [7, 8, 9, 10]
    assert filtra(ATTI, tipo="diffida", al=date(2024, 12, 31)) == []


def test_si_cerca_per_parole_e_si_dice_perche():
    trovati = cerca("provvisoria esecuzione", ATTI)
    assert [t.atto.numero for t in trovati[:2]] == [5, 10]
    assert trovati[0].pagine == {1: ["esecu", "provv"], 2: ["esecu", "provv"]}
    # Nell'atto 01 le due radici stanno su pagine diverse: «non ha
    # provveduto», «nella fase esecutiva». Viene dopo.
    assert trovati[2].atto.numero == 1
    assert trovati[2].pagine == {1: ["provv"], 2: ["esecu"]}


# [/libro:prova-ricerca]


def test_le_dieci_domande_del_pilota():
    # Le domande con il precedente atteso, di tests/domande.json. Misurato
    # l'8 ottobre 2026: 10 su 10 al primo posto. La ricerca del pilota, con
    # un indice più raffinato, ne metteva 9 su 10 (tests/test_ricerca.py).
    domande = json.loads((RADICE / "tests/domande.json").read_text("utf-8"))
    primi = [
        f"{cerca(d['domanda'], ATTI)[0].atto.numero:02d}" == d["atteso"]
        for d in domande
    ]
    assert sum(primi) == 10


def test_un_atto_senza_data_non_sta_in_nessun_periodo():
    senza = AttoLetto(11, "ricorso decreto ingiuntivo", "sarti", None, [])
    assert filtra([senza], dal=date(2020, 1, 1)) == []
    assert filtra([senza], al=date(2030, 1, 1)) == []
    assert filtra([senza], tipo="ricorso") == [senza]


def test_al_modello_va_l_etichetta_non_il_nome_del_file():
    passi = passi_dell_archivio("provvisoria esecuzione", ATTI)
    assert [p.documento for p in passi] == ["archivio-05"] * 2 + [
        "archivio-10"
    ]
    assert etichetta(3) == "archivio-03"


def test_la_domanda_del_fascicolo_trova_un_altro_cliente():
    # L'errore deliberato della lezione 22: la domanda sulla fornitura di
    # Ristorazione Collinare, fatta all'archivio, porta l'atto 01.
    passi = passi_dell_archivio(
        "La resistente ha contestato la fornitura?", ATTI
    )
    assert "archivio-01" in [p.documento for p in passi]


def test_l_indice_dice_chi_nascondere():
    persone = leggi_indice(ARCHIVIO / "indice.csv")
    assert persone["01-2019-sarti-imballaggi-bassi"] == [
        "Imballaggi Bassi S.r.l.",
        "Supermercati Lanza S.p.A.",
    ]
    assert tipo_del_nome("Edil Frignano S.r.l.") == "SOGGETTO"
    assert tipo_del_nome("Ottavio Rinaldi") == "PERSONA"
