"""I costi del fornitore e il tetto del mese (lezione 31)."""

from __future__ import annotations

import json
import os
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app import manage
from app import registro as app_registro
from app.config import ConfigError, load_settings
from app.costi import ModelloConTetto, riepilogo
from app.db import UsoAI, Utente
from app.invio import modello_da
from app.registro import RichiestaNonAmmessa, costo_stimato
from minuta.model import ModelloFinto, Risposta


class ModelloDelFornitore(ModelloFinto):
    def __init__(self, nome):
        super().__init__()
        self.nome = nome
        self.chiamate = 0

    def scrivi(self, sistema, richiesta):
        self.chiamate += 1
        return Risposta("ok", self.nome, 10, 10)


def utente(db, nome_utente):
    return db.scalar(select(Utente).where(Utente.nome_utente == nome_utente))


def spende(db, nome_utente, costo, modello="gpt-6.1-sol"):
    db.add(
        UsoAI(
            utente_id=utente(db, nome_utente).id,
            modello=modello,
            categorie="",
            scopo="prova",
            impronta="0" * 64,
            caratteri=0,
            controllo="",
            costo_usd=costo,
        )
    )
    db.commit()


@pytest.fixture
def contratto(monkeypatch, tmp_path):
    def scrivi(regione):
        file = tmp_path / "contratto.json"
        file.write_text(json.dumps({"regione": regione}), "utf-8")
        monkeypatch.setattr(app_registro, "CONTRATTO", file)

    return scrivi


def test_la_regione_europea_costa_il_dieci_per_cento_in_piu(contratto):
    contratto("standard")
    standard = costo_stimato("gpt-6.1-sol", 2125, 3107)
    contratto("europea")
    assert costo_stimato("gpt-6.1-sol", 2125, 3107) == pytest.approx(
        standard * 1.1, abs=1e-6
    )
    # di un modello senza maggiorazione nel listino non si stima niente
    assert costo_stimato("gpt-6-luna", 2125, 3107) is None


# [libro:prova-tetto]
def test_il_tetto_ferma_le_richieste_prima_che_partano(app):
    with app.state.session_factory() as db:
        spende(db, "sarti", 4.0)
    url = app.state.settings.database_url
    vero = ModelloDelFornitore("gpt-6.1-sol")
    ModelloConTetto(vero, 5.0, url).scrivi("s", "r")  # 4 su 5: parte
    with app.state.session_factory() as db:
        spende(db, "sarti", 1.0)
    with pytest.raises(RichiestaNonAmmessa, match="5,00 dollari su 5,00"):
        ModelloConTetto(vero, 5.0, url).scrivi("s", "r")
    sconosciuto = ModelloDelFornitore("un-altro-modello")
    with pytest.raises(RichiestaNonAmmessa, match="non ha il prezzo"):
        ModelloConTetto(sconosciuto, 100.0, url).scrivi("s", "r")
    assert (vero.chiamate, sconosciuto.chiamate) == (1, 0)


# [/libro:prova-tetto]


def test_un_tetto_di_zero_ferma_anche_il_finto(app):
    url = app.state.settings.database_url
    ModelloConTetto(ModelloFinto(), 1.0, url).scrivi("s", "una domanda")
    with pytest.raises(RichiestaNonAmmessa, match="Tetto del mese"):
        ModelloConTetto(ModelloFinto(), 0.0, url).scrivi("s", "una domanda")


def test_il_tetto_si_imposta_nell_ambiente(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "SECRET_KEY=" + "x" * 48 + "\nDATABASE_URL=sqlite:///x.db\n"
        "APP_ORIGIN=http://127.0.0.1:8000\nALLOWED_HOSTS=127.0.0.1\n",
        "utf-8",
    )
    for valore, atteso in (("", None), ("0", 0.0), ("12,50", 12.5)):
        monkeypatch.setenv("MINUTA_TETTO_MENSILE", valore)
        impostazioni = load_settings(env)
        assert impostazioni.tetto_mensile == atteso
    for sbagliato in ("dieci", "-1"):
        monkeypatch.setenv("MINUTA_TETTO_MENSILE", sbagliato)
        with pytest.raises(ConfigError, match="MINUTA_TETTO_MENSILE"):
            load_settings(env)
    monkeypatch.setenv("MINUTA_TETTO_MENSILE", "3")
    assert isinstance(modello_da(load_settings(env)), ModelloConTetto)
    monkeypatch.delenv("MINUTA_TETTO_MENSILE")
    assert isinstance(modello_da(load_settings(env)), ModelloFinto)


def test_i_costi_del_mese(app, capsys):
    with app.state.session_factory() as db:
        spende(db, "sarti", 0.5)
        spende(db, "irene", 0.25)
        spende(db, "irene", None, "finto-deterministico")
        mese = datetime.now(UTC).strftime("%Y-%m")
        r = riepilogo(db, mese)
        manage.costi_dalla_riga(db, Namespace(mese=None, da="sarti"))
        with pytest.raises(manage.CommandError, match="un avvocato"):
            manage.costi_dalla_riga(db, Namespace(mese=None, da="irene"))
    assert (r["voci"], r["senza_stima"]) == (3, 1)
    assert r["totale"] == pytest.approx(0.75)
    assert r["persona"] == {"Elena Sarti": 0.5, "Irene": 0.25}
    uscita = capsys.readouterr().out.splitlines()
    assert uscita[0] == f"La spesa del fornitore, {mese}: 0,75 dollari."
    assert uscita[1] == "Voci del registro: 3; senza un costo stimato: 1."


@pytest.mark.skipif(os.name != "posix", reason="i permessi Unix")
def test_chi_puo_leggere_il_file_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=x\n", "utf-8")
    env.chmod(0o644)
    assert "lo leggono anche altri utenti" in manage.permessi_env(env)
    env.chmod(0o640)  # anche il gruppo è «altri utenti»
    assert (
        "permessi 640: lo leggono anche altri utenti"
        in manage.permessi_env(env)
    )
    env.chmod(0o600)
    assert "soltanto il suo proprietario" in manage.permessi_env(env)
    assert manage.permessi_env(Path(tmp_path / "manca")) is None
