"""Gli esempi stampati nel libro, rifatti dal laboratorio: se il codice cambia
comportamento, la prova fallisce e la pagina va aggiornata."""

import importlib.util
import json
from pathlib import Path

from minuta import draft
from minuta.model import ModelloFinto

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


def test_lezione_8_la_riga_vera_ha_i_campi_che_il_pilota_scrive(db, fascicolo, config, profilo,
                                                              massimario, tmp_path):
    # La riga stampata viene dal registro del pilota del 6 ottobre 2026: se il
    # codice cambia i campi della riga, la prova fallisce e la pagina va rifatta.
    stampata = json.loads((ESEMPI / "08-riga-del-registro.json").read_text("utf-8"))
    draft.prepara(db, fascicolo, config, profilo, massimario, ModelloFinto(), tmp_path)
    scritta = json.loads((tmp_path / "uso-ai.jsonl").read_text("utf-8").splitlines()[-1])
    assert list(stampata) == list(scritta)
    assert stampata["controllo_fughe"] == "superato" and stampata["approvata_da"] is None


def test_lezione_8_il_registro_dice_superato():
    uscita = carica("genera_08").uscita()
    assert uscita == (ESEMPI / "08-registro-del-paragrafo.json").read_text("utf-8")
    # Il controllo passa e la riga non contiene il testo: niente, nel registro,
    # rivela il nome che la lezione 4 ha lasciato passare.
    assert json.loads(uscita)["controllo_fughe"] == "superato"
    assert "Bellini" not in uscita
    assert "Marco Bellini" in carica("genera_04").uscita()
