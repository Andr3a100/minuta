import base64
import json
import shutil
import subprocess
import sys
from datetime import date, datetime

import pytest
from conftest import RADICE
from lxml import etree

from minuta import __main__ as comandi
from minuta import archive, draft, fatture
from minuta.model import ModelloFinto

sys.path.insert(0, str(RADICE / "strumenti"))
import genera_fatture as genera  # noqa: E402

OGGI = date(2026, 10, 6)
CONSUMATORE = {"nome": "Mario", "cognome": "Ferretti", "cf": "FRRMRA80A01F257Z",
               "indirizzo": "Via Giardini", "civico": "40", "cap": "41124", "comune": "Modena",
               "provincia": "MO"}


def scrivi(tmp_path, nome, cessionario=genera.CESSIONARIO, documenti=genera.FATTURE[:1]):
    xml = genera.fattura(genera.CEDENTE, cessionario, documenti)
    genera.valida(xml)
    (tmp_path / nome).write_bytes(xml)
    return tmp_path / nome


def dal_file(*percorsi):
    return fatture.fascicolo([fatture.leggi(p) for p in percorsi], "2026-041", "sarti", OGGI)


def test_le_fatture_di_prova_rispettano_lo_schema_ufficiale():
    for percorso in sorted((RADICE / "archivio/fatture").glob("*.xml")):
        genera.valida(percorso.read_bytes())
    sbagliata = genera.fattura(genera.CEDENTE, genera.CESSIONARIO, genera.FATTURE[:1]).replace(
        b"<Divisa>EUR</Divisa>", b"")
    with pytest.raises(etree.DocumentInvalid):  # lo schema si fa sentire davvero
        genera.valida(sbagliata)


def test_il_fascicolo_dalle_fatture_coincide_con_quello_di_prova():
    dati = dal_file(*sorted((RADICE / "archivio/fatture").glob("*.xml")))
    prova = json.loads((RADICE / "tests/fascicolo-prova.json").read_text("utf-8"))
    for parte in ("ricorrente", "intimata"):
        assert dati[parte]["nome"] == prova[parte]["nome"]
        assert dati[parte]["piva"] == prova[parte]["piva"]
    assert dati["intimata"]["sede"] == prova["intimata"]["sede"]
    assert [(f["numero"], f["data"], f["importo"]) for f in dati["fatture"]] == [
        (f["numero"], f["data"], f["importo"]) for f in prova["fatture"]]
    assert [f["scadenze"] for f in dati["fatture"]] == [["2025-12-14"], ["2026-01-04"]]
    assert dati["interessi"] == "commerciali" and draft.totale(dati) == 9960.5
    assert dati["documenti"][:3] == [
        "fatture n. 455/2025 e n. 489/2025",
        "documenti di trasporto n. 112 del 10.11.2025 e n. 127 del 02.12.2025",
        "ordini n. 33/2025 del 02.10.2025 e n. 38/2025 del 05.11.2025"]
    assert dati["giudice"].startswith("[DA COMPLETARE") and dati["diffida"] is None


def test_una_nota_di_credito_riduce_il_credito(tmp_path):
    nota = {"tipo": "TD04", "numero": "12/2026", "data": "2026-01-20", "totale": "120.00",
            "descrizione": "Storno parziale per copie difettose", "collegata": "489/2025"}
    dati = dal_file(scrivi(tmp_path, "f.xml", documenti=genera.FATTURE + [nota]))
    assert [n["numero"] for n in dati["note_di_credito"]] == ["12/2026"]
    assert draft.totale(dati) == 9840.5
    assert any("riferita a: 489/2025" in a for a in dati["avvertenze"])
    assert "NOTE DI CREDITO: n. 12/2026 del 20.01.2026 (euro 120,00)" in draft.dati_del_fascicolo(dati, "x")
    assert "TOTALE: 9.840,50" in draft.dati_del_fascicolo(dati, "x")


def test_un_debitore_senza_partita_iva(tmp_path, db, config, profilo, massimario):
    dati = dal_file(scrivi(tmp_path, "f.xml", cessionario=CONSUMATORE))
    assert dati["intimata"] == {"nome": "Mario Ferretti", "piva": "", "cf": "FRRMRA80A01F257Z",
                                "sede": "Via Giardini 40, Modena (MO)", "persona_fisica": True}
    assert dati["interessi"] == "da verificare"
    assert any("consumatore" in a for a in dati["avvertenze"])
    sensibili = draft.sensibili_del_fascicolo(dati)
    assert "" not in sensibili and sensibili["FRRMRA80A01F257Z"] == "CF"
    assert sensibili["Mario Ferretti"] == "PERSONA"
    bozza = draft.prepara(db, dati, config, profilo, massimario, ModelloFinto(), tmp_path)
    for dato in ("FRRMRA80A01F257Z", "Ferretti", "Via Giardini"):
        assert dato not in bozza.inviato
    assert "Ferretti" in bozza.testo  # ricomposto in locale, nella bozza per l'avvocato


def test_le_avvertenze_per_l_avvocato(tmp_path):
    non_scaduta = dict(genera.FATTURE[0], numero="500/2026", scadenza="2026-11-30")
    senza_scadenza = {k: v for k, v in genera.FATTURE[1].items() if k != "scadenza"}
    ridotta = dict(genera.FATTURE[0], numero="501/2026", da_pagare="5472.00")
    dati = dal_file(scrivi(tmp_path, "f.xml", documenti=[non_scaduta, senza_scadenza, ridotta]))
    avvertenze = " | ".join(dati["avvertenze"])
    assert "fattura n. 500/2026: scade il 30.11.2026, non è ancora scaduta" in avvertenze
    assert "fattura n. 489/2025: la fattura non indica la scadenza" in avvertenze
    assert "fattura n. 501/2026: da pagare euro 5.472,00 su un totale di euro 6.840,00" in avvertenze


def test_piu_fatture_nello_stesso_file_e_il_totale_che_manca(tmp_path):
    percorso = scrivi(tmp_path, "f.xml", documenti=genera.FATTURE)
    xml = percorso.read_bytes().replace(b"<ImportoTotaleDocumento>3120.50</ImportoTotaleDocumento>", b"")
    genera.valida(xml)  # il totale è facoltativo nello schema
    percorso.write_bytes(xml)
    letto = fatture.leggi(percorso)
    assert [d["numero"] for d in letto["documenti"]] == ["455/2025", "489/2025"]
    assert letto["documenti"][1]["importo"] == 3120.5  # dal riepilogo IVA


def test_parti_diverse_non_fanno_un_fascicolo(tmp_path):
    prima = scrivi(tmp_path, "a.xml")
    seconda = scrivi(tmp_path, "b.xml", cessionario=CONSUMATORE)
    with pytest.raises(ValueError, match="non sono tutte fra le stesse parti"):
        dal_file(prima, seconda)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="serve openssl")
def test_la_fattura_firmata(tmp_path):
    xml = scrivi(tmp_path, "f.xml")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout",
                    str(tmp_path / "chiave.pem"), "-out", str(tmp_path / "cert.pem"), "-days", "1",
                    "-subj", "/CN=Prova Minuta"], check=True, capture_output=True)
    subprocess.run(["openssl", "smime", "-sign", "-binary", "-nodetach", "-in", str(xml),
                    "-signer", str(tmp_path / "cert.pem"), "-inkey", str(tmp_path / "chiave.pem"),
                    "-outform", "DER", "-out", str(tmp_path / "f.xml.p7m")], check=True, capture_output=True)
    (tmp_path / "base64.xml.p7m").write_bytes(base64.encodebytes((tmp_path / "f.xml.p7m").read_bytes()))
    for nome in ("f.xml.p7m", "base64.xml.p7m"):
        assert fatture.leggi(tmp_path / nome)["documenti"][0]["numero"] == "455/2025"
    (tmp_path / "rotta.xml.p7m").write_bytes(b"non sono una firma")
    with pytest.raises(ValueError, match="non riesco ad aprire il file firmato"):
        fatture.leggi(tmp_path / "rotta.xml.p7m")


def test_dal_comando_fascicolo_alla_bozza(config, tmp_path, monkeypatch, capsys):
    (tmp_path / "config").mkdir()
    for nome in ("studio.json", "profilo.json", "massimario.json"):
        shutil.copy(RADICE / "config" / nome, tmp_path / "config" / nome)
    archive.importa(RADICE / "archivio/pdf", archive.apri(tmp_path / "minuta.db"), config)
    monkeypatch.setattr(comandi, "RADICE", tmp_path)
    xml = [str(p) for p in sorted((RADICE / "archivio/fatture").glob("*.xml"))]
    assert comandi.main(["fascicolo", *xml, "--numero", "2026-041", "--avvocato", "sarti"]) == 0
    assert "2 fatture, credito di euro 9.960,50" in capsys.readouterr().out
    fascicolo = tmp_path / "fascicoli/2026-041.json"

    class Fermo(datetime):  # due bozze nello stesso secondo: nessuna si perde
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 6, 14, 30, 0)

    monkeypatch.setattr(comandi, "datetime", Fermo)
    for _ in range(2):
        assert comandi.main(["bozza", str(fascicolo), "--modello", "finto",
                             "--uscita", str(tmp_path / "bozze")]) == 0
    bozze = sorted(p.name for p in (tmp_path / "bozze").glob("*.md"))
    assert bozze == ["2026-041-20261006-143000-2.md", "2026-041-20261006-143000.md"]
    assert "scadenza 14.12.2025" in (tmp_path / "bozze" / bozze[1]).read_text("utf-8")
