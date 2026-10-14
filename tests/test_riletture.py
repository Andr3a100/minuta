"""Ciò che invecchia nei file di config (lezione 33)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from minuta.riletture import da_rileggere, della_cartella, tra_mesi

CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_i_mesi():
    assert tra_mesi(date(2026, 10, 14), 6) == date(2027, 4, 14)
    assert tra_mesi(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert tra_mesi(date(2026, 12, 1), 1) == date(2027, 1, 1)


def test_le_letture_vecchie_e_i_cambi_vicini():
    dati = {
        "termini": [
            {"nome": "a", "norma": "art. 1", "letta_il": "2026-01-10"},
            {"nome": "b", "letta_il": "2026-06-01"},
            {
                "nome": "c",
                "dal": "2027-01-01",
                "rinvio": "da verificare",
                "computo": "civile",
            },
            {"nome": "d", "fino_al": "2027-12-31"},
            {"nome": "e", "fino_al": "2026-01-01"},
        ],
        "letto_il": "2025-12-01",
    }
    voci = da_rileggere("prova.json", dati, date(2026, 10, 14))
    nomi = {(v.nome, v.che_cosa) for v in voci}
    assert nomi == {
        ("tutto il file", "letta"),
        ("a, art. 1", "letta"),
        ("c", "dal"),
    }
    cambio = next(v for v in voci if v.che_cosa == "dal")
    assert cambio.da_verificare == ["rinvio"]
    # Al limite dei sei mesi, una lettura va rifatta.
    limite = [{"nome": "f", "letta_il": "2026-04-14"}]
    assert da_rileggere("p", limite, date(2026, 10, 14))[0].nome == "f"
    assert da_rileggere("p", limite, date(2026, 10, 13)) == []


def test_il_tributario_cambia_il_primo_gennaio():
    """Il caso vero dei termini: il ricorso tributario passa dal D.Lgs.
    546/1992 al testo unico, e la nuova regola ha voci da verificare."""
    voci = della_cartella(CONFIG, date(2026, 10, 14))
    cambi = [(v.quando, v.che_cosa) for v in voci if v.file == "termini.json"]
    assert (date(2026, 12, 31), "fino_al") in cambi
    assert (date(2027, 1, 1), "dal") in cambi
    nuova = next(v for v in voci if v.che_cosa == "dal")
    assert "rinvio" in nuova.da_verificare
    assert "D.Lgs. 175/2024" in nuova.nome
