"""La bozza (lezione 24): la provenienza di ogni paragrafo, le date e gli
importi che i documenti non hanno, i segnaposto rimasti."""

from __future__ import annotations

import json
from datetime import date

import pytest

from minuta.bozza import (
    TipoDiBozza,
    citazioni,
    controlla,
    da_completare,
    da_verificare,
    istruzioni,
    leggi_bozza,
    manca_la_scadenza,
    pertinenza,
)
from minuta.citations import Massimario

DOCUMENTI = {
    "decreto.pdf": [
        "Ingiunge di pagare euro 14.280,00. Modena, 15 settembre 2026"
    ],
    "promemoria.docx": ["Servono la contabile del bonifico di luglio."],
}
SCADENZE = "- termine per l'opposizione: lunedì 2 novembre 2026 (art. 641)"


def test_ogni_paragrafo_porta_la_sua_provenienza():
    paragrafi = leggi_bozza(
        "TRIBUNALE DI MODENA {fonte: stile}\n\n"
        "Il decreto ingiunge euro 14.280,00. {fonte: decreto.pdf, pagina 1}"
        "\n\nUn paragrafo senza fonte."
    )
    assert [p.fonte for p in paragrafi] == [
        "stile",
        "decreto.pdf, pagina 1",
        None,
    ]
    assert paragrafi[1].testo == "Il decreto ingiunge euro 14.280,00."


# [libro:prova-bozza]
def test_date_e_importi_devono_stare_nei_documenti():
    paragrafi = controlla(
        leggi_bozza(
            "Il decreto del 15 settembre 2026 ingiunge euro 14.280,00; "
            "l'opposizione entro il 2 novembre 2026. "
            "{fonte: decreto.pdf, pagina 1}\n\n"
            "La cliente ha pagato euro 5.000,00 il 15 luglio 2026. "
            "{fonte: promemoria.docx, pagina 1}"
        ),
        DOCUMENTI,
        SCADENZE,
    )
    assert paragrafi[0].problemi == []
    assert paragrafi[1].problemi == [
        "data che non è nei documenti: mercoledì 15 luglio 2026",
        "importo che non è nei documenti: 5.000,00",
    ]


def test_la_fonte_deve_essere_nel_fascicolo():
    (fuori, oltre, senza) = controlla(
        leggi_bozza(
            "Uno. {fonte: sentenza.pdf, pagina 1}\n\n"
            "Due. {fonte: decreto.pdf, pagina 3}\n\nTre."
        ),
        DOCUMENTI,
        SCADENZE,
    )
    assert fuori.problemi == [
        "la fonte non è nel fascicolo: sentenza.pdf, pagina 1"
    ]
    assert oltre.problemi == [
        "la fonte non è nel fascicolo: decreto.pdf, pagina 3"
    ]
    assert senza.problemi == ["nessuna provenienza: da dove viene?"]


# [/libro:prova-bozza]


def test_piu_fonti_in_un_paragrafo_e_le_date_delle_norme():
    (paragrafo,) = controlla(
        leggi_bozza(
            "Ai sensi dell'art. 14 del D.P.R. 30 maggio 2002, n. 115, il "
            "valore è di euro 14.280,00. {fonte: decreto.pdf, pagina 1} "
            "{fonte: stile} {fonte: sentenza.pdf, pagina 2}"
        ),
        DOCUMENTI,
        SCADENZE,
    )
    assert paragrafo.fonte == (
        "decreto.pdf, pagina 1; stile; sentenza.pdf, pagina 2"
    )
    assert "{fonte" not in paragrafo.testo
    assert paragrafo.problemi == [
        "la fonte non è nel fascicolo: sentenza.pdf, pagina 2"
    ]


def test_un_segnaposto_rimasto_si_segnala():
    (paragrafo,) = controlla(
        leggi_bozza("difesa dall'Avv. [PERSONA], [INDIRIZZO] {fonte: stile}"),
        DOCUMENTI,
        SCADENZE,
    )
    assert paragrafo.problemi == [
        "segnaposto rimasto: [PERSONA], da sostituire",
        "segnaposto rimasto: [INDIRIZZO], da sostituire",
    ]


def test_cio_che_manca_e_cio_che_va_verificato():
    paragrafi = leggi_bozza(
        "[DA COMPLETARE: i motivi] {fonte: modello}\n\n"
        "[DA VERIFICARE] il giudice competente. {fonte: modello}"
    )
    assert da_completare(paragrafi) == ["i motivi"]
    assert da_verificare(paragrafi) == ["il giudice competente"]


def test_il_promemoria_deve_dire_entro_quando():
    scadenza = [date(2026, 11, 2)]
    con = leggi_bozza("C'è tempo fino al 2 novembre 2026. {fonte: scadenze}")
    senza = leggi_bozza("C'è tempo. {fonte: scadenze}")
    assert not manca_la_scadenza(con, scadenza)
    assert manca_la_scadenza(senza, scadenza)


def test_solo_le_bozze_che_minuta_sa_preparare():
    assert istruzioni("promemoria").startswith("BOZZA DEL PROMEMORIA:")
    with pytest.raises(TipoDiBozza):
        istruzioni("appello")


# [libro:prova-citazioni]
def test_la_sentenza_che_nessuno_ha_letto(tmp_path):
    voci = {
        "c.p.c. art. 641": {"chiave": "c.p.c. art. 641", "stato": "verificata"}
    }
    (tmp_path / "massimario.json").write_text(json.dumps(voci), "utf-8")
    paragrafi = leggi_bozza(
        "Entro il termine dell'art. 641 c.p.c. {fonte: modello}\n\n"
        "Si propone ai sensi dell'art. 645 c.p.c. {fonte: modello}\n\n"
        "Lo dice Cass. civ., sez. II, 15 maggio 2023, n. 99999. "
        "{fonte: modello}"
    )
    da_leggere = citazioni(paragrafi, Massimario(tmp_path / "massimario.json"))
    assert da_leggere == ["c.p.c. art. 645"]
    assert paragrafi[2].problemi == [
        "sentenza che il massimario non ha: «Cass. civ., sez. II, 15 maggio "
        "2023, n. 99999»; non si cita una sentenza che nessuno ha letto"
    ]


def test_la_norma_che_esiste_ma_non_c_entra():
    paragrafi = leggi_bozza(
        "Provvisoriamente esecutivo ai sensi dell'art. 642, primo comma, "
        "c.p.c., perché il credito è fondato su un assegno. {fonte: modello}"
    )
    pertinenza(paragrafi, DOCUMENTI)
    assert paragrafi[0].problemi == [
        "parla di assegno o cambiale, che il fascicolo non ha: la norma "
        "esiste, ma c'entra?",
        "parla di provvisoria esecuzione, che il fascicolo non ha: la norma "
        "esiste, ma c'entra?",
    ]


# [/libro:prova-citazioni]


def test_la_data_di_una_sentenza_non_e_un_fatto():
    (paragrafo,) = controlla(
        leggi_bozza("Cass. civ., 15 maggio 2023, n. 1. {fonte: modello}"),
        DOCUMENTI,
        SCADENZE,
    )
    assert paragrafo.problemi == []


def test_cio_che_il_fascicolo_ha_non_si_segnala():
    documenti = {"decreto.pdf": ["Decreto provvisoriamente esecutivo."]}
    paragrafi = leggi_bozza("La provvisoria esecuzione. {fonte: modello}")
    pertinenza(paragrafi, documenti)
    assert paragrafi[0].problemi == []
