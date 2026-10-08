"""Le verifiche (lezione 20): le somme rifatte, le domande riempite.

Le somme si rifanno sulle due scansioni della cartella di Ivo Marchetti:
a 100 punti per pollice la lettura ottica legge 5,68 per 5,88 (lezione 16),
a 300 punti legge giusto.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from percorsi import RADICE

from minuta import documenti
from minuta.scheda import Riga
from minuta.verifiche import (
    TipoSconosciuto,
    carica_domande,
    controlla_somme,
    importo_a_fine_riga,
    prepara,
    tipo_di,
)

CARTELLA = RADICE / "documenti-di-prova" / "2026-072"
DOMANDE = carica_domande()


def letto(nome: str) -> str:
    percorso = CARTELLA / nome
    return documenti.leggi(percorso.name, percorso.read_bytes()).testo


# [libro:prova-somme]
def test_la_somma_della_scansione_a_100_punti_non_torna():
    # L'errore della lezione 16: un 8 letto come un 6.
    assert controlla_somme(letto("cartella-scansione.pdf")) == [
        (
            False,
            "le voci fanno 4.837,46, il totale dice 4.837,66: "
            "0,20 di differenza",
        )
    ]
    assert controlla_somme(letto("cartella-scansione-300.pdf")) == [
        (True, "le 4 voci fanno il totale, 4.837,66")
    ]


# [/libro:prova-somme]


def test_gli_importi_come_li_scrive_la_lettura_ottica():
    assert importo_a_fine_riga("Imposta 3,412, 00") == Decimal("3412.00")
    assert importo_a_fine_riga("Totale da pagare 4,837,66") == Decimal(
        "4837.66"
    )
    assert importo_a_fine_riga("Sanzioni 1.023,60") == Decimal("1023.60")
    assert importo_a_fine_riga("reso esecutivo il 14 luglio 2026") is None
    assert importo_a_fine_riga("N. 070 2026 00418265 31 000") is None


def test_una_riga_senza_importo_chiude_l_elenco():
    pagina = "Acconto 100,00\nNota senza cifre\nSaldo 50,00\nTotale 50,00"
    assert controlla_somme(pagina) == [
        (True, "le 1 voci fanno il totale, 50,00")
    ]


def test_le_domande_si_riempiono_senza_risposte():
    righe = [
        Riga("date", "Data della notificazione: 18 settembre 2026", 1),
        Riga(
            "date",
            "Data dell'atto: 18 settembre 2026",
            1,
            tolta_da="Paola Righi",
        ),
    ]
    scadenze = ["ricorso: martedì 17 novembre 2026, da verificare"]
    domande = prepara(
        "cartella di pagamento",
        DOMANDE,
        [letto("cartella-scansione-300.pdf")],
        righe,
        scadenze,
    )
    assert [d["stato"] for d in domande] == ["aperta"] * 3
    assert domande[0]["controlli"] == [
        "pagina 1: le 4 voci fanno il totale, 4.837,66"
    ]
    assert domande[1]["fatti"] == [
        "Data della notificazione: 18 settembre 2026 (pagina 1)"
    ]
    assert domande[2]["controlli"] == scadenze
    senza = prepara("cartella di pagamento", DOMANDE, [""], None, [])
    assert senza[1]["fatti"] == ["la scheda non è confermata: nessun fatto"]
    assert senza[2]["controlli"] == ["nessuna scadenza calcolata"]


def test_il_tipo_di_atto_e_le_sue_norme():
    assert tipo_di(DOMANDE, "cartella") == "cartella di pagamento"
    with pytest.raises(TipoSconosciuto):
        tipo_di(DOMANDE, "appello")
    for elenco in DOMANDE["tipi"].values():
        for domanda in elenco:
            assert domanda["domanda"].endswith("?")  # domande, non risposte
            if "norma" in domanda:
                assert domanda["fonte"].startswith(
                    "https://www.normattiva.it/"
                )
                assert domanda["letta_il"]
