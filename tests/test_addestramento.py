"""L'insieme di addestramento (lezione 28): la forma degli atti, mai i
fatti dei clienti."""

from __future__ import annotations

from minuta.addestramento import fatti_rimasti, senza_fatti


# [libro:prova-senza-fatti]
def test_via_i_fatti_restano_le_norme():
    testo = (
        "la ricorrente ha emesso la fattura n. 301/2023 del 29.09.2023 "
        "(euro 4.880,00), pagata il 3 marzo 2024 per 1.200,00 nell'autunno "
        "2023; interessi ai sensi del D.Lgs. 9 ottobre 2002, n. 231, "
        "dell'art. 14 D.P.R. 115/2002 e degli artt. 633 e 634 c.p.c."
    )
    assert fatti_rimasti(testo) == [
        "data 29/09/2023",
        "data 03/03/2024",
        "importo 1.200,00",
        "importo 4.880,00",
    ]
    pulito = senza_fatti(testo)
    assert pulito == (
        "la ricorrente ha emesso la fattura n. [NUMERO] del [DATA] "
        "(euro [IMPORTO]), pagata il [DATA] per [IMPORTO] nell'autunno "
        "[ANNO]; interessi ai sensi del D.Lgs. 9 ottobre 2002, n. 231, "
        "dell'art. 14 D.P.R. 115/2002 e degli artt. 633 e 634 c.p.c."
    )
    assert fatti_rimasti(pulito) == []


# [/libro:prova-senza-fatti]


def test_le_altre_forme_delle_norme_restano():
    for norma in (
        "legge n. 132/2025",
        "D.P.R. 30 maggio 2002, n. 115",
        "DM 110/2023",
        "Decreto legislativo 175/2024",
    ):
        assert senza_fatti(f"secondo la {norma}.") == f"secondo la {norma}."
        assert fatti_rimasti(norma) == []


def test_un_numero_di_documento_andato_a_capo():
    assert senza_fatti("le fatture n.\n322/2023 e n. 7") == (
        "le fatture n. [NUMERO] e n. [NUMERO]"
    )


def test_una_norma_con_la_sola_data_e_un_importo_senza_centesimi():
    assert senza_fatti(
        "il D.P.R. 30 maggio 2002 sulle spese; euro 40 l'una"
    ) == ("il D.P.R. 30 maggio 2002 sulle spese; euro [IMPORTO] l'una")
