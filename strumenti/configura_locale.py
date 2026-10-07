"""Prepara il file .env di Minuta sul computer dello studio.

    python strumenti/configura_locale.py

Se il file non c'è, lo crea, leggibile solo da te, con un segreto casuale e
il database SQLite locale. Se c'è, aggiunge in fondo solo le impostazioni
che mancano: non tocca le righe che ci sono e non mostra nessun valore. La
chiave del fornitore del modello, se c'è già, resta dov'è.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

# [libro:configura]
PREDEFINITI = {
    "APP_ENV": "development",
    "SECRET_KEY": "",  # generato a caso, qui sotto
    "DATABASE_URL": "sqlite:///./studio.db",
    "APP_ORIGIN": "http://127.0.0.1:8000",
    "ALLOWED_HOSTS": "127.0.0.1,localhost",
    "SESSION_HOURS": "8",
}
# [/libro:configura]


def nomi_presenti(file: Path) -> set[str]:
    """I nomi già impostati nel file, senza leggerne i valori."""
    if not file.is_file():
        return set()
    nomi = set()
    for riga in file.read_text(encoding="utf-8").splitlines():
        riga = riga.strip()
        if riga and not riga.startswith("#") and "=" in riga:
            nomi.add(riga.split("=", 1)[0].strip())
    return nomi


def main(file: Path = Path(".env")) -> int:
    mancanti = [n for n in PREDEFINITI if n not in nomi_presenti(file)]
    if not mancanti:
        print(f"{file}: la configurazione c'è già, non la modifico.")
        return 0
    valori = {**PREDEFINITI, "SECRET_KEY": secrets.token_urlsafe(48)}
    righe = "".join(f"{nome}={valori[nome]}\n" for nome in mancanti)
    if not file.exists():
        # O_EXCL: fallisce se il file nel frattempo è comparso; 0o600: lo
        # legge e lo scrive solo il proprietario.
        descrittore = os.open(
            file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descrittore, "w", encoding="utf-8") as uscita:
            uscita.write(
                "# Configurazione locale di Minuta. Non condividerla.\n"
            )
            uscita.write(righe)
        print(f"Creato {file} con il database locale e un segreto casuale.")
        return 0
    testo = file.read_text(encoding="utf-8")
    with file.open("a", encoding="utf-8") as uscita:
        if testo and not testo.endswith("\n"):
            uscita.write("\n")
        uscita.write("# Aggiunte da strumenti/configura_locale.py\n")
        uscita.write(righe)
    print(
        f"Aggiunte a {file}: {', '.join(mancanti)}. I valori non si mostrano."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
