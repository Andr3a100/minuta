"""I controlli di salute e le intestazioni di sicurezza."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.migrations import migra, ultima


def test_pronto_solo_con_lo_schema_giusto(app_vuota):
    with TestClient(app_vuota) as client:
        assert client.get("/salute").json()["stato"] == "ok"
        assert client.get("/pronto").status_code == 503
        migra(app_vuota.state.engine)
        pronto = client.get("/pronto").json()
        assert pronto == {"stato": "pronto", "schema": ultima()}


def test_le_pagine_portano_le_protezioni(browser):
    risposta = browser().get("/accesso")
    assert risposta.headers["x-frame-options"] == "DENY"
    assert risposta.headers["x-content-type-options"] == "nosniff"
    assert (
        "frame-ancestors 'none'" in risposta.headers["content-security-policy"]
    )


def test_un_host_sconosciuto_e_respinto(app):
    with TestClient(app, base_url="http://altrosito.example") as client:
        assert client.get("/salute").status_code == 400
