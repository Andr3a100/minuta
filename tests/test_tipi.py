"""I tipi di atto come configurazione (lezione 40)."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from minuta.bozza import TIPI, istruzioni
from minuta.scadenze import calcola, carica_regole
from minuta.tipi import carica_tipi, esamina
from minuta.verifiche import carica_domande, tipo_di

RADICE = Path(__file__).resolve().parents[1]
DOMANDE, REGOLE = carica_domande(), carica_regole()
PRECETTO = next(t for t in carica_tipi() if t["nome"] == "atto di precetto")


def righe(esame):
    return {voce: (ok, dettaglio) for voce, ok, dettaglio in esame.righe}


def test_il_precetto_è_completo_senza_codice_nuovo():
    esame = esamina(PRECETTO, DOMANDE, REGOLE, TIPI)
    assert esame.completo
    r = righe(esame)
    assert r["domande"] == (True, "5, 3 con la norma letta")
    assert r["termine"][1].endswith("da verificare: sospensione_feriale")
    assert tipo_di(DOMANDE, "atto") == "atto di precetto"
    assert "art. 617 c.p.c." in istruzioni("opposizione agli atti esecutivi")


def test_ogni_parte_mancante_si_vede(tmp_path):
    tipo = {
        **PRECETTO,
        "domande": "nessuno",
        "bozze": ["ricorso", "promemoria"],
    }
    tipo["termine"] = "nessuno"
    tipo["prova"] = "documenti-di-prova/nessuno.pdf"
    r = righe(esamina(tipo, DOMANDE, REGOLE, TIPI))
    assert r["domande"] == (False, "mancano in verifiche.json")
    assert r["termine"] == (False, "manca in termini.json")
    assert r["bozze"] == (False, "mancano in bozze.json: ricorso")
    assert r["prova"] == (False, "manca")


def test_una_norma_senza_data_non_è_una_regola():
    domande = copy.deepcopy(DOMANDE)
    del domande["tipi"]["atto di precetto"][0]["letta_il"]
    regole = copy.deepcopy(REGOLE)
    for regola in regole["termini"]:
        if regola["nome"] == "opposizione agli atti esecutivi":
            regola["fonte"] = ""
    r = righe(esamina(PRECETTO, domande, regole, TIPI))
    assert r["domande"] == (False, "una norma senza fonte o data")
    assert r["termine"] == (False, "una norma senza fonte o data")


def test_l_avviso_del_penale_resta_da_completare():
    esami = {
        e.nome: e
        for e in (esamina(t, DOMANDE, REGOLE, TIPI) for t in carica_tipi())
    }
    assert not esami["avviso di conclusione delle indagini"].completo
    assert esami["decreto ingiuntivo"].completo
    assert esami["cartella di pagamento"].completo


def test_la_regola_dell_art_617():
    fuori_agosto = calcola("opposizione agli atti", date(2027, 10, 4), REGOLE)
    assert fuori_agosto.scadenza == date(2027, 10, 25)  # il 24 è domenica
    in_agosto = calcola("opposizione agli atti", date(2027, 7, 20), REGOLE)
    assert in_agosto.scadenza is None
    assert "sospensione feriale è da verificare" in in_agosto.da_decidere


def test_le_bozze_vengono_dalla_configurazione():
    dati = json.loads((RADICE / "config" / "bozze.json").read_text("utf-8"))
    assert TIPI == dati["bozze"]
    assert list(TIPI)[:2] == ["opposizione", "promemoria"]


def test_lo_script_della_regola_copiata():
    uscita = subprocess.run(
        [sys.executable, str(RADICE / "percorso" / "regola_copiata.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    assert "Con la regola copiata: giovedì 9 settembre 2027." in uscita
    assert "Se la sospensione non vale: lunedì 9 agosto 2027." in uscita
    assert "Con la regola letta: decide l'avvocato" in uscita
