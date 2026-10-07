"""Le basi della Parte 0: i file che il lettore scrive, provati come nel libro.

La prova automatica dei tre sistemi esegue le sessioni intere; queste prove
tengono fermi, a ogni modifica del laboratorio, i risultati che il testo
del libro descrive.
"""

import shutil
import subprocess
import sys
from pathlib import Path

BASI = Path(__file__).resolve().parent.parent / "basi"


def esegui(cartella, *argomenti):
    return subprocess.run(
        [sys.executable, *argomenti],
        cwd=cartella,
        capture_output=True,
        text=True,
        timeout=120,
    )


def conti(tmp_path):
    for nome in ("primo_conto.py", "conti.py", "test_conti.py"):
        shutil.copy(BASI / "conti" / nome, tmp_path / nome)
    return tmp_path


def test_b5_il_primo_conto(tmp_path):
    assert esegui(conti(tmp_path), "primo_conto.py").stdout == "63.0\n"


def test_b5_i_sei_test_passano(tmp_path):
    esito = esegui(conti(tmp_path), "-m", "pytest", "-q")
    assert esito.returncode == 0, esito.stdout
    assert esito.stdout.startswith("......")
    assert "6 passed" in esito.stdout


def test_b5_la_mediana_che_e_una_media(tmp_path):
    cartella = conti(tmp_path)
    file = cartella / "conti.py"
    giusta = '"mediana": statistics.median(minuti)'
    testo = file.read_text(encoding="utf-8")
    assert testo.count(giusta) == 1
    file.write_text(
        testo.replace(giusta, '"mediana": statistics.mean(minuti)'),
        encoding="utf-8",
    )
    esito = esegui(cartella, "-m", "pytest", "-q")
    assert esito.stdout.startswith("FF....")
    assert "{'mediana': 126} != {'mediana': 125}" in esito.stdout
    assert "{'mediana': 265} != {'mediana': 132.5}" in esito.stdout
    assert "2 failed, 4 passed" in esito.stdout


def test_b5_le_funzioni_al_volo(tmp_path):
    cartella = conti(tmp_path)
    riassunto = esegui(
        cartella,
        "-c",
        "from conti import riassunto; "
        "print(riassunto([95, 140, 210, 60, 125]))",
    )
    assert riassunto.stdout == "{'misure': 5, 'media': 126, 'mediana': 125}\n"
    negativi = esegui(
        cartella, "-c", "from conti import ore; print(ore(-1, 126))"
    )
    assert negativi.returncode == 1
    assert negativi.stderr.splitlines()[-1] == (
        "ValueError: i fascicoli non possono essere negativi"
    )
