"""Il glossario del fascicolo (lezione 29)."""

from __future__ import annotations

from minuta.domande import scegli_passi
from minuta.glossario import scegli_con_glossario
from minuta.valutazione import pagine_del_fascicolo

FORNO = "La resistente ha contestato la fornitura?"


# [libro:prova-glossario]
def test_il_forno_parte_se_l_avvocato_lo_dice():
    pagine = pagine_del_fascicolo("2026-071")
    senza = scegli_con_glossario(FORNO, pagine, {})
    con = scegli_con_glossario(FORNO, pagine, {"fornitura": ["forno"]})
    assert [p.documento for p in senza] == [
        "fattura-112.xml.p7m",
        "fattura-141.xml.p7m",
        "ricorso.pdf",
    ]
    assert [p.documento for p in con] == [
        "fattura-112.xml.p7m",
        "promemoria.docx",
        "ricorso.pdf",
    ]


# [/libro:prova-glossario]


def test_una_voce_che_non_c_entra_non_cambia_niente():
    pagine = pagine_del_fascicolo("2026-071")
    domanda = "Quale somma ingiunge il decreto?"
    assert scegli_con_glossario(domanda, pagine, {"fornitura": ["forno"]}) == (
        scegli_passi(domanda, pagine)
    )


def test_sempre_al_massimo_tre_pagine_le_equivalenti_prima():
    documenti = {f"d{n}.pdf": [f"il forno numero {n}"] for n in range(5)}
    documenti["altro.pdf"] = ["la fornitura della cucina contestata"]
    scelti = scegli_con_glossario(FORNO, documenti, {"fornitura": ["forno"]})
    assert [p.documento for p in scelti] == ["d0.pdf", "d1.pdf", "d2.pdf"]


def test_una_pagina_parte_una_volta_sola():
    documenti = {"a.pdf": ["il forno e la fornitura contestata"]}
    scelti = scegli_con_glossario(FORNO, documenti, {"fornitura": ["forno"]})
    assert [p.documento for p in scelti] == ["a.pdf"]
