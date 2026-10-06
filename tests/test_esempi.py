"""Gli esempi stampati nel libro, rifatti dal laboratorio: se il codice cambia
comportamento, la prova fallisce e la pagina va aggiornata."""

import importlib.util
from pathlib import Path

ESEMPI = Path(__file__).resolve().parents[1] / "esempi"


def carica(nome):
    spec = importlib.util.spec_from_file_location(nome, ESEMPI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_lezione_4_il_nome_che_nessuno_ha_messo_in_elenco():
    uscita = carica("genera_04").uscita()
    assert uscita == (ESEMPI / "04-paragrafo-pseudonimizzato.txt").read_text("utf-8")
    # Ciò che il fascicolo conosce è nascosto; il resto passa, e la prova delle
    # fughe non se ne accorge: è il limite che la lezione 17 deve chiudere.
    assert "Alessandro Riva" not in uscita and "Logistica Riva" not in uscita
    assert "Marco Bellini" in uscita and "Carpi" in uscita and "frattura del bacino" in uscita
    assert uscita.rstrip().endswith("Controllo delle fughe: superato")
