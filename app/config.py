"""Configurazione di Minuta.

I valori arrivano dalle variabili d'ambiente. Sul computer dello studio
possono stare nel file .env della cartella da cui avvii il programma: una
variabile già presente nell'ambiente ha sempre la precedenza sul file. Nello
stesso file sta la chiave del fornitore del modello, che questo modulo non
legge e non mostra.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

AMBIENTI = ("development", "test", "production")


class ConfigError(Exception):
    """Configurazione assente o non sicura: il programma non deve partire."""


# [libro:file-env]
def leggi_file_env(percorso: Path) -> dict[str, str]:
    """Legge righe NOME=valore, ignorando righe vuote e commenti."""
    valori: dict[str, str] = {}
    if not percorso.is_file():
        return valori
    testo = percorso.read_text(encoding="utf-8")
    for numero, riga in enumerate(testo.splitlines(), start=1):
        riga = riga.strip()
        if not riga or riga.startswith("#"):
            continue
        nome, uguale, valore = riga.partition("=")
        if not uguale:
            raise ConfigError(f"{percorso}, riga {numero}: manca il segno =")
        valore = valore.strip()
        if len(valore) >= 2 and valore[0] == valore[-1] and valore[0] in "\"'":
            valore = valore[1:-1]  # toglie le virgolette esterne
        valori[nome.strip()] = valore
    return valori


# [/libro:file-env]


@dataclass(frozen=True)
class Settings:
    app_env: str
    secret_key: str
    database_url: str
    app_origin: str
    allowed_hosts: tuple[str, ...]
    session_hours: int = 8
    # Gli originali dei documenti e l'elenco dei certificatori (lezione 16).
    data_dir: str = "dati"

    @property
    def production(self) -> bool:
        return self.app_env == "production"

    # [libro:controlli-config]
    def validate(self) -> Settings:
        """Rifiuta le configurazioni che renderebbero il servizio insicuro."""
        if self.app_env not in AMBIENTI:
            raise ConfigError("APP_ENV deve essere: " + ", ".join(AMBIENTI))
        if len(self.secret_key) < 40:
            raise ConfigError("SECRET_KEY deve contenere almeno 40 caratteri")
        if not self.database_url:
            raise ConfigError("DATABASE_URL mancante")
        if not self.app_origin:
            raise ConfigError("APP_ORIGIN mancante")
        if not self.allowed_hosts:
            raise ConfigError("ALLOWED_HOSTS mancante")
        if not self.data_dir:
            raise ConfigError("DATA_DIR mancante")
        if not 1 <= self.session_hours <= 24:
            raise ConfigError("SESSION_HOURS deve essere tra 1 e 24")
        if self.production and not self.app_origin.startswith("https://"):
            raise ConfigError("In produzione APP_ORIGIN usa https://")
        return self

    # [/libro:controlli-config]


def load_settings(file_env: str | os.PathLike[str] = ".env") -> Settings:
    """Combina il file .env e le variabili d'ambiente, poi controlla tutto."""
    valori = leggi_file_env(Path(file_env))
    valori.update(os.environ)  # l'ambiente vince sul file
    host = tuple(
        h.strip()
        for h in valori.get("ALLOWED_HOSTS", "").split(",")
        if h.strip()
    )
    try:
        ore = int(valori.get("SESSION_HOURS", "8"))
    except ValueError:
        raise ConfigError(
            "SESSION_HOURS deve essere un numero intero"
        ) from None
    return Settings(
        app_env=valori.get("APP_ENV", "development"),
        secret_key=valori.get("SECRET_KEY", ""),
        database_url=valori.get("DATABASE_URL", ""),
        app_origin=valori.get("APP_ORIGIN", "").rstrip("/"),
        allowed_hosts=host,
        session_hours=ore,
        data_dir=valori.get("DATA_DIR", "dati"),
    ).validate()
