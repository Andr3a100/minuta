"""Le domande sul fascicolo (lezione 21): i passi scelti, le citazioni
controllate, il «non c'è»."""

from __future__ import annotations

import pytest
from percorsi import RADICE

from minuta import documenti
from minuta.domande import (
    Frase,
    RispostaIlleggibile,
    controlla,
    leggi_risposta,
    normale,
    scegli_passi,
)


def fascicolo(codice: str) -> dict[str, list[str]]:
    cartella = RADICE / "documenti-di-prova" / codice
    return {
        p.name: [
            pagina.testo
            for pagina in documenti.leggi(p.name, p.read_bytes()).pagine
        ]
        for p in sorted(cartella.iterdir())
    }


PENALE = fascicolo("2026-073")
CIVILE = fascicolo("2026-071")
AVVISO = "avviso-415-bis.pdf.p7m"


# [libro:prova-domande]
def test_senza_le_parole_della_domanda_non_parte_niente():
    assert scegli_passi("Che cosa dice il consulente tecnico?", PENALE) == []


def test_la_citazione_deve_stare_alla_pagina_mandata():
    passi = scegli_passi("Quali facoltà ha l'indagato?", PENALE)
    frasi = controlla(
        [
            Frase(
                "Memorie.",
                AVVISO,
                1,
                "di presentare memorie, produrre documenti",
            ),
            Frase("Memorie.", AVVISO, 1, "di presentare memorie scritte"),
            Frase("Il decreto.", "decreto.pdf", 1, "INGIUNGE"),
        ],
        passi,
    )
    assert [f.problemi for f in frasi] == [
        [],
        [f"la citazione non è a pagina 1 di {AVVISO}"],
        ["decreto.pdf, pagina 1: non è fra i passi mandati"],
    ]


# [/libro:prova-domande]


def test_una_frase_senza_citazione_si_segnala():
    passi = scegli_passi("Quali facoltà ha l'indagato?", PENALE)
    (frase,) = controlla([Frase("Memorie.", AVVISO, 1, "")], passi)
    assert frase.problemi == ["nessuna citazione: da dove viene?"]


def test_la_ricerca_per_parole_non_trova_il_forno():
    # Il limite della lezione 21: il promemoria parla di «forno», la
    # domanda di «fornitura», e il promemoria non parte.
    passi = scegli_passi("La resistente ha contestato la fornitura?", CIVILE)
    assert "ricorso.pdf" in [p.documento for p in passi]
    assert "promemoria.docx" not in [p.documento for p in passi]


def test_la_risposta_puo_dire_che_non_c_e():
    frasi, manca = leggi_risposta(
        '{"frasi": [], "non_c_e": "la data della notifica"}'
    )
    assert frasi == [] and manca == "la data della notifica"
    for sbagliata in ("Non so.", '{"frasi": []}', '{"frasi": ["una"]}'):
        with pytest.raises(RispostaIlleggibile):
            leggi_risposta(sbagliata)


def test_apostrofi_e_virgolette_di_un_tipo_solo():
    assert normale("L’indagato  ha\nfacoltà «di»") == normale(
        'l\'indagato ha facoltà "di"'
    )
