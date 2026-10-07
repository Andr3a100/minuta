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


# Lezione B7: i file SQL, eseguiti istruzione per istruzione nell'ordine del
# libro, con il modulo sqlite3 di Python, su un database che dura fra un
# file e l'altro come quello del lettore.


def istruzioni(nome):
    testo = (BASI / "sql" / nome).read_text(encoding="utf-8")
    pezzi = [p.strip() for p in testo.split(";")]
    vere = lambda p: any(
        r.strip() and not r.strip().startswith("--") for r in p.splitlines()
    )
    return [p for p in pezzi if vere(p)]


def esegui_file(db, nome):
    import sqlite3

    esiti = []
    for istruzione in istruzioni(nome):
        try:
            esiti.append(db.execute(istruzione).fetchall())
        except sqlite3.IntegrityError as errore:
            esiti.append(errore)
    return esiti


def test_b7_i_fatti_che_la_lezione_descrive(tmp_path):
    import sqlite3

    db = sqlite3.connect(tmp_path / "fascicoli.db", isolation_level=None)
    db.executescript((BASI / "sql" / "fascicoli.sql").read_text("utf-8"))

    persone, tre_colonne, aperte, ordinate = esegui_file(db, "leggere.sql")
    assert len(persone) == 4
    assert len(tre_colonne) == 5
    assert [c for c, _ in aperte] == ["F-01", "F-03", "F-05"]
    assert [c for c, _ in ordinate] == ["F-03", "F-02", "F-05", "F-01", "F-04"]

    medie, gruppi = esegui_file(db, "contare.sql")
    assert medie == [(5, 126.0, 110.0)]
    assert gruppi == [("civile", 2), ("penale", 1), ("tributario", 2)]

    join, left_join = esegui_file(db, "collegare.sql")
    assert len(join) == 4 and "F-04" not in [c for c, _ in join]
    assert ("F-04", None) in left_join and len(left_join) == 5

    _, _, toccate, nuove = esegui_file(db, "modificare.sql")
    assert toccate == [(1,)]
    assert nuove == [("F-05", 125, 1), ("F-06", 960, 0)]

    _, persona_9, lavoro, conteggio = esegui_file(db, "vincoli.sql")
    assert "FOREIGN KEY constraint failed" in str(persona_9)
    assert "CHECK constraint failed" in str(lavoro)
    assert conteggio == [(6,)]

    # L'errore deliberato, sulla copia: sei scadenze documentate.
    copia = sqlite3.connect(tmp_path / "prova.db", isolation_level=None)
    db.backup(copia)
    _, toccate, dopo = esegui_file(copia, "errore.sql")
    assert toccate == [(6,)]
    assert {d for _, d in dopo} == {1}

    # La transazione, sul database vero: l'UPDATE senza WHERE è annullato.
    _, _, toccate, _, dopo = esegui_file(db, "transazione.sql")
    assert toccate == [(6,)]
    assert [c for c, d in dopo if d == 1] == ["F-02", "F-04", "F-05"]

    # La risposta attesa dal prompt: i fascicoli di Paola Righi.
    paola = "(SELECT id FROM persone WHERE nome = 'Paola Righi')"
    assert db.execute(
        "SELECT count(*), avg(minuti_studio) FROM fascicoli "
        f"WHERE studiato_da = {paola}"
    ).fetchall() == [(2, 132.5)]
