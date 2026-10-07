"""La configurazione e lo strumento che la prepara."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from app.config import ConfigError, Settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "strumenti"))
import configura_locale  # noqa: E402


def impostazioni(**diverse):
    valori = {
        "app_env": "development",
        "secret_key": "s" * 40,
        "database_url": "sqlite:///./studio.db",
        "app_origin": "http://127.0.0.1:8000",
        "allowed_hosts": ("127.0.0.1",),
        **diverse,
    }
    return Settings(**valori)


def test_un_segreto_corto_ferma_tutto():
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        impostazioni(secret_key="corto").validate()


def test_in_produzione_solo_https():
    with pytest.raises(ConfigError, match="https"):
        impostazioni(app_env="production").validate()


def test_il_file_nuovo_lo_legge_solo_chi_lo_crea(tmp_path, capsys):
    file = tmp_path / ".env"
    configura_locale.main(file)
    testo = file.read_text("utf-8")
    assert "SECRET_KEY=" in testo and "DATABASE_URL=sqlite" in testo
    if os.name == "posix":
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert (
        testo.split("SECRET_KEY=")[1].split()[0] not in capsys.readouterr().out
    )


def test_la_chiave_del_fornitore_resta_com_era(tmp_path, capsys):
    file = tmp_path / ".env"
    chiave = "OPENAI_API_KEY=sk-prova-da-non-mostrare\n"
    file.write_text("# la chiave\n" + chiave, "utf-8")
    configura_locale.main(file)
    testo = file.read_text("utf-8")
    assert testo.startswith("# la chiave\n" + chiave)  # non toccata
    assert testo.count("SECRET_KEY=") == 1
    uscita = capsys.readouterr().out
    assert "sk-prova" not in uscita and "OPENAI_API_KEY" not in uscita
    configura_locale.main(file)  # la seconda volta non aggiunge niente
    assert file.read_text("utf-8") == testo
