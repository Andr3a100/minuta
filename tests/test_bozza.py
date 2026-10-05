import json

import pytest

from minuta import draft
from minuta.leaks import fughe
from minuta.model import ModelloFinto
from minuta.pseudonym import Pseudonimizzatore


def prepara(db, fascicolo, config, profilo, massimario, tmp_path, errore=None):
    return draft.prepara(db, fascicolo, config, profilo, massimario,
                         ModelloFinto(errore=errore), tmp_path)


def test_al_modello_non_arriva_niente_di_riconoscibile(db, fascicolo, config, profilo,
                                                       massimario, tmp_path):
    bozza = prepara(db, fascicolo, config, profilo, massimario, tmp_path)
    sensibili = list(draft.sensibili_del_fascicolo(fascicolo)) + ["Elena Sarti", "Taddei"]
    assert fughe(bozza.inviato, sensibili) == []
    assert "[SOGGETTO_1]" in bozza.inviato


def test_la_bozza_ha_i_nomi_veri_e_la_provenienza(db, fascicolo, config, profilo,
                                                  massimario, tmp_path):
    bozza = prepara(db, fascicolo, config, profilo, massimario, tmp_path)
    assert "Officine Grafiche Taddei S.r.l." in bozza.testo
    assert "Hotel Belvedere Sestola S.r.l." in bozza.testo
    assert bozza.esempi[0] == "07"  # il precedente più vicino, nello stile di Sarti
    assert all(p["fonte"] != "non dichiarata" for p in bozza.paragrafi)
    assert all(c["stato"] == "verificata" for c in bozza.citazioni)
    assert not [a for a in bozza.avvisi if a.startswith(("PERTINENZA", "CONTAMINAZIONE"))]


def test_ogni_chiamata_e_registrata(db, fascicolo, config, profilo, massimario, tmp_path):
    prepara(db, fascicolo, config, profilo, massimario, tmp_path)
    voce = json.loads((tmp_path / "uso-ai.jsonl").read_text("utf-8").splitlines()[-1])
    assert voce["fascicolo"] == "2026-041"
    assert voce["controllo_fughe"] == "superato"
    assert voce["approvata_da"] is None
    assert len(voce["inviato_sha256"]) == 64


def test_errore_deliberato_la_sentenza_inventata(db, fascicolo, config, profilo,
                                                 massimario, tmp_path):
    bozza = prepara(db, fascicolo, config, profilo, massimario, tmp_path, errore="sentenza")
    assert any("sentenza non presente nel massimario" in a for a in bozza.avvisi)


def test_errore_deliberato_il_segnaposto_di_un_altro_cliente(db, fascicolo, config, profilo,
                                                            massimario, tmp_path):
    bozza = prepara(db, fascicolo, config, profilo, massimario, tmp_path, errore="contaminazione")
    assert any(a.startswith("CONTAMINAZIONE") for a in bozza.avvisi)
    # Il segnaposto resta tale: non diventa mai il nome di un altro cliente.
    assert "[E1_SOGGETTO_2]" in bozza.testo


def test_errore_deliberato_un_precedente_non_pertinente(db, fascicolo, config, profilo,
                                                        massimario, tmp_path):
    fascicolo["rapporto"] = "la fornitura di materiale edile pagata con assegno poi protestato"
    bozza = prepara(db, fascicolo, config, profilo, massimario, tmp_path)
    assert any(a.startswith("PERTINENZA: la bozza parla di provvisoria esecuzione")
               for a in bozza.avvisi)


def test_l_invio_si_blocca_se_qualcosa_sfugge(db, fascicolo, config, profilo, massimario,
                                              tmp_path, monkeypatch):
    monkeypatch.setattr(Pseudonimizzatore, "nascondi", lambda self, testo: testo)
    with pytest.raises(RuntimeError, match="invio bloccato"):
        prepara(db, fascicolo, config, profilo, massimario, tmp_path)
    assert not (tmp_path / "uso-ai.jsonl").exists()


def test_errore_deliberato_i_40_euro_dimenticati(db, fascicolo, config, profilo, massimario,
                                                tmp_path):
    completa = prepara(db, fascicolo, config, profilo, massimario, tmp_path)
    assert "euro 80,00 per i costi di recupero" in completa.testo
    assert not [a for a in completa.avvisi if a.startswith("COMPLETEZZA")]
    incompleta = prepara(db, fascicolo, config, profilo, massimario, tmp_path, errore="incompleto")
    assert any("40 euro per ciascuna fattura (2 fatture, euro 80,00)" in a and "C-585/20" in a
               for a in incompleta.avvisi)


def test_le_regole_dello_studio_arrivano_al_modello(db, fascicolo, config, profilo, massimario,
                                                    tmp_path):
    bozza = prepara(db, fascicolo, config, profilo, massimario, tmp_path)
    assert "REGOLE DELLO STUDIO:" in bozza.inviato
    assert "qui 2 fatture, euro 80,00" in bozza.inviato
    assert "cgue C-585/20" in bozza.inviato  # fra le citazioni ammesse
