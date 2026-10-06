"""I casi ricavati dalle norme, non dall'agente (lezione 13)."""

from datetime import date

from scadenze import scadenza_opposizione


def test_sospensione_feriale_2026():
    # 16 giorni a luglio, agosto sospeso, 24 a settembre (L. 742/1969, art. 1).
    assert scadenza_opposizione(date(2026, 7, 15)) == date(2026, 9, 24)


def test_sabato_e_ognissanti_2026():
    # Quaranta giorni dal 21 settembre: sabato 31 ottobre; domenica 1 novembre,
    # Ognissanti; lunedì 2 novembre (art. 155, commi 4 e 5, c.p.c.).
    assert scadenza_opposizione(date(2026, 9, 21)) == date(2026, 11, 2)
