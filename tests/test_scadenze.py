"""Le scadenze (lezione 19): il calcolo con le regole di config/termini.json.

Le date attese si contano a mano sul calendario; le regole vengono dalle
norme lette su Normattiva, citate nel file.
"""

from __future__ import annotations

from datetime import date

import pytest

from minuta.scadenze import (
    TermineSconosciuto,
    calcola,
    carica_regole,
    festivo,
    in_lettere,
    pasqua,
)

REGOLE = carica_regole()
OPPOSIZIONE = "opposizione al decreto ingiuntivo"
CARTELLA = "ricorso contro la cartella di pagamento"
AVVISO = "facoltà dopo l'avviso di conclusione delle indagini"


# [libro:prova-scadenze]
@pytest.mark.parametrize(
    "termine, notificazione, scadenza",
    [
        (OPPOSIZIONE, date(2026, 9, 21), date(2026, 11, 2)),  # sabato, santi
        (CARTELLA, date(2026, 9, 18), date(2026, 11, 17)),
        (OPPOSIZIONE, date(2026, 7, 20), date(2026, 9, 29)),  # agosto fermo
        (OPPOSIZIONE, date(2027, 2, 7), date(2027, 3, 19)),  # S. Giuseppe no
        (AVVISO, date(2027, 9, 14), date(2027, 10, 5)),  # S. Francesco sì
        (AVVISO, date(2026, 10, 11), date(2026, 10, 31)),  # sabato penale
    ],
)
def test_le_scadenze_si_contano_a_mano(termine, notificazione, scadenza):
    assert calcola(termine, notificazione, REGOLE).scadenza == scadenza


def test_dove_le_regole_non_bastano_decide_l_avvocato():
    # Il caso della lezione 13: il 31 luglio 2027 è sabato, e la proroga
    # cadrebbe in agosto.
    proroga = calcola(OPPOSIZIONE, date(2027, 6, 21), REGOLE)
    assert proroga.scadenza is None
    assert "la proroga porta la scadenza in agosto" in proroga.da_decidere


# [/libro:prova-scadenze]


def test_ogni_passaggio_cita_la_sua_norma():
    calcolo = calcola(OPPOSIZIONE, date(2026, 9, 21), REGOLE)
    assert calcolo.passaggi == [
        "40 giorni dalla notificazione: art. 641, primo comma, c.p.c., "
        "letta il 2026-10-07",
        "partenza lunedì 21 settembre 2026, che non si conta "
        "(art. 155 c.p.c.)",
        "il 40° giorno è sabato 31 ottobre 2026",
        "è sabato: la scadenza passa a domenica 1° novembre 2026 "
        "(art. 155 c.p.c.)",
        "è Ognissanti: la scadenza passa a lunedì 2 novembre 2026 "
        "(art. 155 c.p.c.)",
    ]


def test_cio_che_e_da_verificare_ferma_il_calcolo():
    # Nel tributario la sospensione feriale è da verificare.
    agosto = calcola(CARTELLA, date(2026, 6, 20), REGOLE)
    assert agosto.scadenza is None
    assert "sospensione feriale è da verificare" in agosto.da_decidere
    # Dal 2027 vale il testo unico, e il suo rinvio al c.p.c. è da trovare.
    nel_2027 = calcola(CARTELLA, date(2027, 1, 18), REGOLE)
    assert nel_2027.norma == "art. 67, D.Lgs. 175/2024"
    assert nel_2027.scadenza is None
    assert "rinvio" in nel_2027.da_decidere


def test_ogni_regola_porta_la_norma_letta_sulla_fonte():
    for regola in REGOLE["termini"]:
        assert regola["fonte"].startswith("https://www.normattiva.it/")
        assert regola["norma"] and regola["letta_il"]
    for norma in REGOLE["festivi"]["norme"]:
        assert norma["fonte"].startswith("https://www.normattiva.it/")


def test_il_calendario_dei_festivi():
    festivi = REGOLE["festivi"]
    assert pasqua(2026) == date(2026, 4, 5)
    assert pasqua(2027) == date(2027, 3, 28)
    assert festivo(date(2026, 4, 6), festivi) == "lunedì dopo Pasqua"
    assert festivo(date(2026, 10, 4), festivi) == (
        "San Francesco, festa nazionale"
    )
    assert festivo(date(2025, 10, 4), festivi) is None  # festa dal 2026
    # San Giuseppe, Pietro e Paolo, 4 novembre: non più festivi (L. 54/1977).
    for giorno in (date(2027, 3, 19), date(2027, 6, 29), date(2026, 11, 4)):
        assert festivo(giorno, festivi) is None
    assert in_lettere(date(2026, 11, 1)) == "domenica 1° novembre 2026"


def test_basta_l_inizio_del_nome_se_e_di_un_termine_solo():
    assert calcola("ricorso", date(2026, 9, 18), REGOLE).termine == CARTELLA
    with pytest.raises(TermineSconosciuto):
        calcola("appello", date(2026, 9, 18), REGOLE)
    doppie = {
        **REGOLE,
        "termini": [*REGOLE["termini"], {"nome": "opposizione X"}],
    }
    with pytest.raises(TermineSconosciuto, match="più termini"):
        calcola("opposizione", date(2026, 9, 21), doppie)
