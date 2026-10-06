# [libro:test-conti]
"""Le prove dei conti: ogni test è un caso che conosciamo già."""

import pytest

from conti import ore, riassunto, saldi


def test_riassunto_dei_cinque_fascicoli():
    # I minuti di studio dei cinque fascicoli della lezione 2.
    assert riassunto([95, 140, 210, 60, 125]) == {
        "misure": 5,
        "media": 126,
        "mediana": 125,
    }


def test_il_fascicolo_che_sposta_la_media():
    # Con il sesto fascicolo, da 960 minuti, la media più che raddoppia.
    assert riassunto([95, 140, 210, 60, 125, 960]) == {
        "misure": 6,
        "media": 265,
        "mediana": 132.5,
    }


def test_riassunto_senza_misure_rifiutato():
    with pytest.raises(ValueError):
        riassunto([])


def test_ore_di_studio_al_mese():
    # Trenta fascicoli al mese da 126 minuti: 63 ore (lezione 3).
    assert ore(30, 126) == 63


def test_fascicoli_negativi_rifiutati():
    with pytest.raises(ValueError):
        ore(-1, 126)


def test_saldi_del_caso_prudente():
    # 8.000 euro di avvio, 1.200 di gestione, 3.600 di beneficio l'anno.
    assert saldi(8000, 1200, 3600, 4) == [-5600, -3200, -800, 1600]


# [/libro:test-conti]
