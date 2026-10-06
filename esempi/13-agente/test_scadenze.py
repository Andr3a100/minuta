# Copiato senza modifiche dalla risposta di gpt-6.1-sol del 7 ottobre 2026
# (verbali/L13-errore-deliberato-2026-10-07.json del libro), lezione 13.

from datetime import date, datetime

import pytest

from scadenze import scadenza_opposizione


@pytest.mark.parametrize(
    ("notifica", "attesa"),
    [
        # Termine ordinario: giorno iniziale escluso.
        (date(2025, 1, 10), date(2025, 2, 19)),

        # Anno bisestile.
        (date(2024, 1, 25), date(2024, 3, 5)),

        # Sabati e domeniche intermedi non sono esclusi.
        (date(2025, 6, 20), date(2025, 7, 30)),

        # Scadenza di sabato o domenica: proroga al lunedì.
        (date(2025, 2, 17), date(2025, 3, 31)),
        (date(2025, 2, 18), date(2025, 3, 31)),

        # Sabato, Pasqua e lunedì dell'Angelo.
        (date(2025, 3, 10), date(2025, 4, 22)),

        # Natale, Santo Stefano e fine settimana.
        (date(2025, 11, 15), date(2025, 12, 29)),

        # Attraversamento della sospensione feriale.
        (date(2025, 7, 10), date(2025, 9, 19)),

        # Notifica durante la sospensione: conteggio dal 1° settembre.
        (date(2025, 8, 1), date(2025, 10, 10)),
        (date(2025, 8, 15), date(2025, 10, 10)),
        (date(2025, 8, 31), date(2025, 10, 10)),

        # Il 31 luglio è sabato; la proroga incontra agosto.
        (date(2021, 6, 21), date(2021, 9, 1)),

        # Cambio di anno.
        (date(2025, 12, 10), date(2026, 1, 19)),

        # San Francesco: il 4 ottobre 2027 è lunedì festivo.
        (date(2027, 7, 25), date(2027, 10, 5)),
    ],
)
def test_scadenza_opposizione(notifica, attesa):
    assert scadenza_opposizione(notifica) == attesa


@pytest.mark.parametrize(
    "notifica",
    [
        None,
        "2025-01-10",
        20250110,
        datetime(2025, 1, 10, 12, 0),
    ],
)
def test_rifiuta_input_non_date(notifica):
    with pytest.raises(TypeError):
        scadenza_opposizione(notifica)


def test_rifiuta_regime_feriale_precedente():
    with pytest.raises(ValueError):
        scadenza_opposizione(date(2014, 7, 10))
