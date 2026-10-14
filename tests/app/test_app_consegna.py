"""Che cosa non si consegna a un altro studio (lezione 39)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest
from aiuti import con_fascicoli

from app import manage
from app.consegna import esamina, file_dello_studio
from app.copie import fai_copia


@pytest.fixture
def radice(tmp_path):
    """Un laboratorio in miniatura: l'intestazione, due testi, un modello
    di pagina."""
    (tmp_path / "config").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "app" / "templates").mkdir(parents=True)
    studio = {
        "studio": "Studio Meridiana",
        "indirizzo": "Via delle Meridiane 12",
        "avvocati": [{"id": "sarti", "nome": "Elena Sarti"}],
    }
    (tmp_path / "config" / "studio.json").write_text(json.dumps(studio))
    (tmp_path / "docs" / "informativa.md").write_text(
        "# Studio Meridiana\nFirma: Elena Sarti.\n"
    )
    (tmp_path / "docs" / "neutro.md").write_text("Minuta, per chiunque.\n")
    (tmp_path / "app" / "templates" / "base.html").write_text(
        "<p>Rosa ha aperto il fascicolo; la rosa dei venti no.</p>"
    )
    return tmp_path


def test_un_installazione_nuova_si_consegna(app_vuota, impostazioni, radice):
    from app.migrations import migra

    migra(app_vuota.state.engine)
    settings = replace(impostazioni, copie_dir=str(radice / "copie"))
    with app_vuota.state.session_factory() as db:
        esame = esamina(db, settings, radice)
    assert esame.si_consegna
    assert set(esame.dati.values()) == {0}
    assert [p for p, _ in esame.file] == [
        "config/studio.json",
        "docs/informativa.md",
    ]
    # Un testo che nomina soltanto un avvocato dell'intestazione.
    (radice / "docs" / "firma.md").write_text("Avv. Elena Sarti\n")
    with app_vuota.state.session_factory() as db:
        esame = esamina(db, settings, radice)
    assert dict(esame.file)["docs/firma.md"] == ["Elena Sarti"]
    # Senza dati, ma con una copia o con la chiave, non si consegna.
    fai_copia(settings, 30, date(2026, 10, 14))
    with app_vuota.state.session_factory() as db:
        assert not esamina(db, settings, radice).si_consegna
    for copia in (radice / "copie").iterdir():
        copia.unlink()
    (radice / ".env").write_text("ANTHROPIC_API_KEY=prova\n")
    with app_vuota.state.session_factory() as db:
        assert not esamina(db, settings, radice).si_consegna


def test_dati_copie_e_chiave_non_si_consegnano(app, impostazioni, radice):
    con_fascicoli(app)
    settings = replace(impostazioni, copie_dir=str(radice / "copie"))
    with app.state.session_factory() as db:
        esame = esamina(db, settings, radice)
        assert not esame.si_consegna
        assert esame.dati["persone dello studio"] == 6
        assert esame.dati["fascicoli"] == 3
        # Le persone di Minuta si cercano per nome intero, con le maiuscole.
        nomi = dict(esame.file)
        assert nomi["app/templates/base.html"] == ["Rosa"]
    vuota = replace(settings, copie_dir=str(radice / "altre"))
    fai_copia(vuota, 30, date(2026, 10, 14))
    (radice / ".env").write_text("SECRET_KEY=x\nOPENAI_API_KEY=sk-prova\n")
    with app.state.session_factory() as db:
        esame = esamina(db, vuota, radice)
    assert (esame.copie, esame.env) == (1, True)
    (radice / ".env").write_text("SECRET_KEY=x\nOPENAI_API_KEY=\n")
    with app.state.session_factory() as db:
        assert esamina(db, vuota, radice).env is False


def test_il_nome_intero_non_un_pezzo(radice):
    (radice / "docs" / "altro.md").write_text(
        "Studio Meridianale, Elena Sartini"
    )
    trovati = dict(
        file_dello_studio(["Studio Meridiana", "Elena Sarti"], radice)
    )
    assert "docs/altro.md" not in trovati


def test_il_comando(app, impostazioni, capsys):
    con_fascicoli(app)
    with app.state.session_factory() as db:
        assert manage.consegna_dalla_riga(db, app.state.settings) == 1
    uscita = capsys.readouterr().out
    assert "  fascicoli                              3" in uscita
    assert "Non si consegna" in uscita
    assert "  docs/informativa.md:" in uscita
