"""La scheda dell'atto in arrivo (lezione 18): che cosa controlla Minuta.

Le prove usano il decreto ingiuntivo di Ristorazione Collinare, una pagina:
il controllo deve trovare ciò che non è alla pagina citata, e la prova del
limite dice ciò che non può trovare.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from percorsi import RADICE

from minuta import documenti
from minuta.invio import SISTEMA, prepara, ricomponi
from minuta.model import ModelloFinto
from minuta.scheda import (
    ISTRUZIONI,
    Riga,
    SchedaIlleggibile,
    a_pagine,
    controlla,
    date_in,
    importi_in,
    leggi_risposta,
)

DECRETO = RADICE / "documenti-di-prova" / "2026-071" / "decreto.pdf"
LETTURA = documenti.leggi(DECRETO.name, DECRETO.read_bytes())
PAGINE = [pagina.testo for pagina in LETTURA.pagine]
NOTI = {
    "Ristorazione Collinare S.r.l.": "SOGGETTO",
    "Termocucine Secchia S.r.l.": "SOGGETTO",
}


def test_le_date_in_lettere_e_in_cifre():
    testo = "Modena, 15 settembre 2026; il 1° ottobre 2026; 15/09/2026"
    assert date_in(testo) == {date(2026, 9, 15), date(2026, 10, 1)}
    assert date_in("il 31/02/2026 non esiste") == set()


def test_gli_importi_e_cio_che_non_lo_e():
    testo = "euro 14.280,00, oltre a 6.100,00 e € 40, per un totale"
    assert importi_in(testo) == {
        Decimal("14280.00"),
        Decimal("6100.00"),
        Decimal("40.00"),
    }
    assert importi_in("art. 633, n. 1873/2026, il 15.09.2026") == set()


# [libro:prova-scheda]
def test_cio_che_non_e_alla_pagina_citata_si_segnala():
    righe = controlla(
        [
            Riga("importi", "Somma ingiunta: euro 14.280,00", 1),
            Riga("importi", "Somma ingiunta: euro 14.208,00", 1),
            Riga("date", "Data del decreto: 16 settembre 2026", 1),
            Riga("parti", "Ricorrente: Termocucine Secchia S.r.l.", 2),
            Riga("date", "Data della notificazione: non risulta", None),
        ],
        PAGINE,
    )
    assert [riga.problemi for riga in righe] == [
        [],
        ["l'importo 14.208,00 non è a pagina 1"],
        ["la data 16/09/2026 non è a pagina 1"],
        ["la pagina 2 non c'è: l'atto ha 1 pagina"],
        [],
    ]


def test_la_data_giusta_al_posto_sbagliato_passa():
    # Il limite del controllo: il 2 settembre è a pagina 1, ma è il deposito
    # del ricorso, non la notificazione. Lo vede soltanto chi legge.
    notifica = Riga("date", "Data della notificazione: 2 settembre 2026", 1)
    assert controlla([notifica], PAGINE)[0].problemi == []


# [/libro:prova-scheda]


def test_una_riga_senza_pagina_o_con_una_voce_inventata_si_segnala():
    righe = controlla(
        [
            Riga("date", "Data dell'atto: 15 settembre 2026", None),
            Riga("umore", "Il giudice era di buon umore", 1),
        ],
        PAGINE,
    )
    assert righe[0].problemi == ["nessuna pagina: da dove viene?"]
    assert righe[1].problemi == ["voce sconosciuta: «umore»"]


def test_la_risposta_si_legge_anche_fra_i_recinti_e_in_ordine_di_voce():
    risposta = (
        "Ecco la scheda:\n```json\n"
        '{"righe": [{"voce": "Date", "testo": " Data  dell\'atto: '
        '15 settembre 2026", "pagina": "1"}, {"voce": "parti", '
        '"testo": "Ricorrente: [SOGGETTO_2]", "pagina": 1.0}]}\n```'
    )
    data, parte = leggi_risposta(risposta)[::-1]
    assert (data.voce, data.testo, data.pagina) == (
        "date",
        "Data dell'atto: 15 settembre 2026",
        1,
    )
    assert parte.voce == "parti" and parte.pagina is None


@pytest.mark.parametrize(
    "risposta",
    [
        "Non posso preparare la scheda.",
        '{"righe": [}',
        '{"righe": []}',
        '{"scheda": "nessuna"}',
        '{"righe": ["una riga"]}',
    ],
)
def test_una_risposta_che_non_e_una_scheda_e_illeggibile(risposta):
    with pytest.raises(SchedaIlleggibile):
        leggi_risposta(risposta)


def test_il_modello_finto_sbaglia_sempre_allo_stesso_modo():
    preparato = prepara(f"{ISTRUZIONI}\n\n{a_pagine(PAGINE)}", NOTI)
    assert not preparato.bloccato
    risposta = ModelloFinto().scrivi(SISTEMA, preparato.testo)
    righe = leggi_risposta(risposta.testo)
    for riga in righe:
        riga.testo = ricomponi(riga.testo, preparato.tabella)
    controlla(righe, PAGINE)
    assert [(r.testo, r.pagina, len(r.problemi)) for r in righe] == [
        ("Controparte: Termocucine Secchia S.r.l.", 2, 1),
        ("Importo: euro 14.208,00", 1, 1),
        ("Data dell'atto: 15 settembre 2026", 1, 0),
        ("Data della notificazione: 2 settembre 2026", 1, 0),
    ]
