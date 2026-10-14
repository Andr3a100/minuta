"""Le copie di sicurezza: fare, verificare, ripristinare (lezione 33)."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tarfile
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from aiuti import con_fascicoli
from sqlalchemy import select

from app import documenti as app_documenti
from app.copie import (
    CONTENUTO,
    CopiaRifiutata,
    fai_copia,
    fascicoli_nelle_copie,
    percorso_database,
    ripristina,
    verifica_copia,
)
from app.db import Fascicolo, Utente

RADICE = Path(__file__).resolve().parents[2]
DECRETO = RADICE / "documenti-di-prova" / "2026-074" / "decreto.pdf"
OGGI = date(2026, 10, 14)


@pytest.fixture
def studio(app, impostazioni, tmp_path):
    """Lo studio con i fascicoli di prova e un documento caricato."""
    con_fascicoli(app)
    settings = replace(impostazioni, copie_dir=str(tmp_path / "copie"))
    with app.state.session_factory() as db:
        sarti = db.scalar(select(Utente).where(Utente.nome_utente == "sarti"))
        fascicolo = db.scalar(
            select(Fascicolo).where(Fascicolo.codice == "2026-071")
        )
        app_documenti.carica(
            db, settings, sarti, fascicolo, "decreto.pdf", DECRETO.read_bytes()
        )
    return settings


def test_la_copia_contiene_database_dati_e_impronte(studio):
    copia = fai_copia(studio, 30, OGGI)
    assert copia.percorso.name == "minuta-2026-10-14.tar.gz"
    assert copia.fascicoli == ["2026-071", "2026-072", "2026-073"]
    assert copia.file == 1  # l'originale del decreto
    with tarfile.open(copia.percorso) as tar:
        nomi = tar.getnames()
        contenuto = json.loads(tar.extractfile(CONTENUTO).read())
    assert nomi[0] == CONTENUTO
    assert "database.sqlite" in nomi
    assert set(contenuto["impronte"]) == set(nomi) - {CONTENUTO}
    assert contenuto["fatta_il"] == "2026-10-14"
    if os.name == "posix":  # leggibile soltanto da chi la crea
        assert copia.percorso.stat().st_mode & 0o777 == 0o600
    # Una seconda copia nello stesso giorno non cancella la prima.
    assert fai_copia(studio, 30, OGGI).percorso.name.endswith("-2.tar.gz")


def test_le_copie_vecchie_si_tolgono(studio):
    vecchia = fai_copia(studio, 30, OGGI - timedelta(days=31)).percorso
    al_limite = fai_copia(studio, 30, OGGI - timedelta(days=30)).percorso
    copia = fai_copia(studio, 30, OGGI)
    assert copia.tolte == [vecchia.name]
    assert not vecchia.exists() and al_limite.exists()
    # Chi cerca un fascicolo nelle copie sa quando l'ultima si toglie.
    giorni = fascicoli_nelle_copie(Path(studio.copie_dir), 30)["2026-071"]
    assert max(giorni) == OGGI + timedelta(days=31)


def test_la_verifica_trova_ogni_guasto(studio, tmp_path):
    copia = fai_copia(studio, 30, OGGI).percorso
    verifica = verifica_copia(copia)
    assert verifica.problemi == []
    assert (verifica.fascicoli, verifica.persone) == (3, 6)

    def rifai(cambia):
        """La stessa copia, con un file cambiato, tolto o aggiunto."""
        guasta = tmp_path / "guasta.tar.gz"
        with tarfile.open(copia) as tar, tarfile.open(guasta, "w:gz") as out:
            for membro in tar.getmembers():
                dati = tar.extractfile(membro).read()
                dati = cambia(membro.name, dati)
                if dati is None:
                    continue
                membro.size = len(dati)
                out.addfile(membro, io.BytesIO(dati))
            extra = cambia("in-più", None)
            if extra:
                info = tarfile.TarInfo("dati/in-più")
                info.size = len(extra)
                out.addfile(info, io.BytesIO(extra))
        return verifica_copia(guasta).problemi

    def documento(nome, dati):
        if nome.startswith("dati/documenti/"):
            return dati[:-1] + b"x"
        return dati

    problemi = rifai(documento)
    assert len(problemi) == 1 and problemi[0].startswith("impronta diversa")
    assert rifai(lambda n, d: None if n.startswith("dati/") else d)[
        0
    ].startswith("manca dati/documenti/")
    assert rifai(lambda n, d: b"!" if n == "in-più" else d) == [
        "file in più: dati/in-più"
    ]

    def database(nome, dati):
        if nome == "database.sqlite":
            return dati[:100] + b"\0" * (len(dati) - 100)
        return dati

    assert any(p.startswith("database") for p in rifai(database))


def test_il_ripristino_in_un_minuta_vuoto(studio, tmp_path, app):
    copia = fai_copia(studio, 30, OGGI).percorso
    server = replace(
        studio,
        database_url=f"sqlite:///{(tmp_path / 'server.db').as_posix()}",
        data_dir=str(tmp_path / "server-dati"),
    )
    verifica = ripristina(server, copia)
    assert verifica.fascicoli == 3
    with sqlite3.connect(percorso_database(server)) as conn:
        codici = [r[0] for r in conn.execute("SELECT codice FROM fascicoli")]
    conn.close()
    assert sorted(codici) == ["2026-071", "2026-072", "2026-073"]
    originali = list((tmp_path / "server-dati" / "documenti").iterdir())
    assert len(originali) == 1
    # Un database che contiene già dati non si sovrascrive.
    with pytest.raises(CopiaRifiutata, match="contiene già dati"):
        ripristina(server, copia)
    with pytest.raises(CopiaRifiutata, match="contiene già dati"):
        ripristina(studio, copia)


def test_il_ripristino_non_sovrascrive_un_file_diverso(studio, tmp_path):
    copia = fai_copia(studio, 30, OGGI).percorso
    server = replace(
        studio,
        database_url=f"sqlite:///{(tmp_path / 'server.db').as_posix()}",
        data_dir=str(tmp_path / "server-dati"),
    )
    with tarfile.open(copia) as tar:
        nome = next(n for n in tar.getnames() if n.startswith("dati/"))
    diverso = tmp_path / "server-dati" / nome.removeprefix("dati/")
    diverso.parent.mkdir(parents=True)
    diverso.write_bytes(b"un altro file")
    with pytest.raises(CopiaRifiutata, match="c'è già, diverso"):
        ripristina(server, copia)
    assert not (tmp_path / "server.db").exists()  # prima i controlli


def test_una_copia_guasta_non_si_ripristina(studio, tmp_path):
    copia = fai_copia(studio, 30, OGGI).percorso
    guasta = tmp_path / "guasta.tar.gz"
    guasta.write_bytes(copia.read_bytes()[:200])
    server = replace(
        studio,
        database_url=f"sqlite:///{(tmp_path / 'server.db').as_posix()}",
    )
    with pytest.raises(CopiaRifiutata, match="non si apre"):
        ripristina(server, guasta)


def test_postgresql_si_copia_con_i_suoi_strumenti(studio):
    altro = replace(studio, database_url="postgresql://studio@localhost/m")
    with pytest.raises(CopiaRifiutata, match="pg_dump"):
        fai_copia(altro, 30, OGGI)


def test_le_copie_vecchie_non_entrano_nella_nuova(studio):
    """Con la cartella delle copie dentro quella dei dati, una copia non
    contiene le copie di prima."""
    dentro = replace(studio, copie_dir=str(Path(studio.data_dir) / "copie"))
    fai_copia(dentro, 30, OGGI)
    seconda = fai_copia(dentro, 30, OGGI)
    assert seconda.file == 1
    with tarfile.open(seconda.percorso) as tar:
        assert not any("copie" in n for n in tar.getnames())


def test_un_nome_che_esce_dalla_cartella_non_si_estrae(studio, tmp_path):
    copia = fai_copia(studio, 30, OGGI).percorso
    ostile = tmp_path / "copie" / "ostile.tar.gz"
    with tarfile.open(copia) as tar, tarfile.open(ostile, "w:gz") as out:
        for membro in tar.getmembers():
            out.addfile(membro, tar.extractfile(membro))
        info = tarfile.TarInfo("../../fuori.txt")
        info.size = 1
        out.addfile(info, io.BytesIO(b"!"))
    with pytest.raises(CopiaRifiutata, match="non si apre"):
        verifica_copia(ostile)
    assert not list(tmp_path.rglob("fuori.txt"))


def test_una_copia_cambiata_non_si_ripristina(studio, tmp_path):
    copia = fai_copia(studio, 30, OGGI).percorso
    cambiata = tmp_path / "cambiata.tar.gz"
    with tarfile.open(copia) as tar, tarfile.open(cambiata, "w:gz") as out:
        for membro in tar.getmembers():
            dati = tar.extractfile(membro).read()
            if membro.name.startswith("dati/"):
                dati = dati[:-1] + b"x"
            out.addfile(membro, io.BytesIO(dati))
    server = replace(
        studio,
        database_url=f"sqlite:///{(tmp_path / 'server.db').as_posix()}",
        data_dir=str(tmp_path / "server-dati"),
    )
    with pytest.raises(CopiaRifiutata, match="non è integra: impronta"):
        ripristina(server, cambiata)
    assert not (tmp_path / "server.db").exists()
