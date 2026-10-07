"""La lettura dei documenti del fascicolo (lezione 16).

Le prove tengono fermi i fatti che il libro racconta: il tipo si riconosce
dal contenuto, la lettura ottica della cartella a 100 punti per pollice
sbaglia una cifra e a 300 no, una busta firmata dice integrità e
certificato separati, e il certificato è verificato solo rispetto
all'elenco dei certificatori, mai rispetto a quelli del sistema.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from minuta import documenti

RADICE = Path(__file__).resolve().parents[1]
PROVA = RADICE / "documenti-di-prova"
sys.path.insert(0, str(RADICE / "strumenti"))
import genera_documenti_di_prova  # noqa: E402


def openssl(*argomenti, entrata: bytes | None = None) -> bytes:
    return subprocess.run(
        ["openssl", *argomenti],
        input=entrata,
        capture_output=True,
        check=True,
    ).stdout


@pytest.fixture
def certificatore(tmp_path):
    """Un certificatore di prova e un firmatario con un suo certificato."""
    c = tmp_path / "pki"
    c.mkdir()
    openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(c / "ca.key"),
        "-out",
        str(c / "ca.pem"),
        "-days",
        "3650",
        "-subj",
        "/CN=Certificatore di prova",
    )
    openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(c / "firma.key"),
        "-out",
        str(c / "firma.csr"),
        "-subj",
        "/CN=Firmatario di prova",
    )
    (c / "est.cnf").write_text(
        "basicConstraints=CA:FALSE\nkeyUsage=nonRepudiation,digitalSignature\n"
    )
    openssl(
        "x509",
        "-req",
        "-in",
        str(c / "firma.csr"),
        "-CA",
        str(c / "ca.pem"),
        "-CAkey",
        str(c / "ca.key"),
        "-CAcreateserial",
        "-out",
        str(c / "firma.pem"),
        "-days",
        "365",
        "-extfile",
        str(c / "est.cnf"),
    )
    return c


def busta(certificatore: Path, contenuto: bytes) -> bytes:
    return openssl(
        "smime",
        "-sign",
        "-binary",
        "-nodetach",
        "-signer",
        str(certificatore / "firma.pem"),
        "-inkey",
        str(certificatore / "firma.key"),
        "-outform",
        "DER",
        entrata=contenuto,
    )


def elenco(cartella: Path, *certificati: Path) -> Path:
    """Una cartella con un elenco dei certificatori, come quello di AgID."""
    cartella.mkdir(parents=True, exist_ok=True)
    pem = "".join(c.read_text() for c in certificati)
    (cartella / "certificatori.pem").write_text(pem)
    notizie = {
        "emesso": "2026-09-24T07:16:56Z",
        "numero": 1,
        "servizi": len(certificati),
        "certificatori": 1,
    }
    (cartella / "certificatori.json").write_text(json.dumps(notizie))
    return cartella


def leggi(percorso: Path, cartella: Path | None = None):
    return documenti.leggi(percorso.name, percorso.read_bytes(), cartella)


def test_il_modello_della_lingua_e_quello_dichiarato():
    leggimi = (RADICE / "tessdata" / "LEGGIMI.md").read_text("utf-8")
    dati = (RADICE / "tessdata" / "ita.traineddata").read_bytes()
    assert hashlib.sha256(dati).hexdigest() in leggimi


def test_il_tipo_si_riconosce_dal_contenuto(certificatore):
    assert (
        documenti.riconosci((PROVA / "2026-071/decreto.pdf").read_bytes())
        == "pdf"
    )
    assert (
        documenti.riconosci((PROVA / "2026-071/promemoria.docx").read_bytes())
        == "word"
    )
    firmata = busta(certificatore, b"<a/>")
    assert documenti.riconosci(firmata) == "busta"
    assert documenti.riconosci(base64.encodebytes(firmata)) == "busta"
    assert documenti.riconosci(b"<?xml version='1.0'?><a/>") == "xml"
    assert documenti.riconosci(b"testo qualsiasi") == "sconosciuto"


def test_il_nome_che_mente_viene_segnalato(certificatore):
    lettura = documenti.leggi("atto.pdf", busta(certificatore, b"<a/>"))
    assert lettura.tipo.startswith("busta firmata")
    assert lettura.avvisi[0].startswith("Il nome finisce in .pdf")


def test_un_pdf_con_il_testo_non_passa_dalla_lettura_ottica():
    lettura = leggi(PROVA / "2026-071/decreto.pdf")
    assert lettura.tipo == "PDF" and not lettura.ottica
    assert "la somma di euro 14.280,00" in lettura.testo
    assert lettura.avvisi == []


def test_la_scansione_a_300_punti_si_legge_esatta():
    lettura = leggi(PROVA / "2026-072/cartella-scansione-300.pdf")
    assert lettura.ottica and lettura.pagine[0].risoluzione == 300
    vera = genera_documenti_di_prova.CARTELLA.split()
    assert lettura.testo.split() == vera
    assert lettura.avvisi == [
        "Pagina 1: lettura ottica, una trascrizione da controllare "
        "sull'immagine."
    ]


def test_la_scansione_a_100_punti_sbaglia_una_cifra():
    # L'errore deliberato della lezione 16: un 8 letto come 6.
    lettura = leggi(PROVA / "2026-072/cartella-scansione.pdf")
    assert lettura.pagine[0].risoluzione == 100
    righe = lettura.testo.splitlines()
    assert "Diritti di notifica 5,68" in righe
    assert "Totale da pagare 4,837,66" in righe
    assert "meno dei 300 consigliati" in lettura.avvisi[0]
    # Le voci trascritte non danno il totale: 20 centesimi di differenza.
    voci = [3412.00, 1023.60, 396.18, 5.68]
    assert round(sum(voci), 2) == 4837.46


def test_word_e_fatture_diventano_testo():
    word = leggi(PROVA / "2026-071/promemoria.docx")
    assert word.tipo == "Word"
    assert "notificato il 21 settembre 2026" in word.testo
    fattura = leggi(PROVA / "2026-071/fattura-112.xml.p7m")
    assert fattura.tipo == "busta firmata con fattura elettronica"
    assert (
        "Fattura n. 112 del 16 febbraio 2026: 6.100,00 euro; "
        "scadenza 18 marzo 2026." in fattura.testo
    )


def test_le_tre_fatture_fanno_la_somma_del_decreto():
    totale = 0.0
    for numero in ("112", "141", "168"):
        lettura = leggi(PROVA / f"2026-071/fattura-{numero}.xml.p7m")
        riga = next(r for r in lettura.testo.splitlines() if "Fattura" in r)
        importo = riga.split(": ")[1].split(" euro")[0]
        totale += float(importo.replace(".", "").replace(",", "."))
    assert round(totale, 2) == 14280.00


def test_busta_integra_ma_certificato_firmato_da_se_stesso(
    tmp_path, certificatore
):
    cartella = elenco(tmp_path / "elenco", certificatore / "ca.pem")
    lettura = leggi(PROVA / "2026-073/avviso-415-bis.pdf.p7m", cartella)
    assert lettura.tipo == "busta firmata con PDF"
    assert lettura.busta.integro is True
    assert lettura.busta.certificato is False
    assert (
        lettura.busta.motivo == "firmato da sé stesso, non da un certificatore"
    )
    assert lettura.busta.firmatario == (
        "Procura della Repubblica di Modena (certificato di prova)"
    )
    assert "giustizia riparativa" in lettura.testo


def test_certificato_verificato_solo_con_il_certificatore_nell_elenco(
    tmp_path, certificatore
):
    firmata = busta(certificatore, b"<a/>")
    dentro = elenco(tmp_path / "con", certificatore / "ca.pem")
    lettura = documenti.leggi("prova.xml.p7m", firmata, dentro)
    assert lettura.busta.certificato is True
    assert lettura.busta.firmatario == "Firmatario di prova"
    altro = tmp_path / "altro"
    altro.mkdir()
    openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(altro / "k.pem"),
        "-out",
        str(altro / "ca.pem"),
        "-days",
        "30",
        "-subj",
        "/CN=Un altro certificatore",
    )
    fuori = elenco(tmp_path / "senza", altro / "ca.pem")
    lettura = documenti.leggi("prova.xml.p7m", firmata, fuori)
    assert lettura.busta.certificato is False
    assert lettura.busta.motivo == "chi l'ha emesso non è nell'elenco di AgID"


def test_i_certificati_del_sistema_non_contano(
    tmp_path, certificatore, monkeypatch
):
    # Il certificatore è fidato per il sistema (come quelli dei siti web),
    # ma non sta nell'elenco: la firma resta non verificata.
    sistema = tmp_path / "sistema"
    sistema.mkdir()
    impronta = (
        openssl(
            "x509", "-hash", "-noout", "-in", str(certificatore / "ca.pem")
        )
        .decode()
        .strip()
    )
    (sistema / f"{impronta}.0").write_bytes(
        (certificatore / "ca.pem").read_bytes()
    )
    monkeypatch.setenv("SSL_CERT_DIR", str(sistema))
    monkeypatch.setenv("SSL_CERT_FILE", str(certificatore / "ca.pem"))
    altro = tmp_path / "altro.pem"
    openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(tmp_path / "k.pem"),
        "-out",
        str(altro),
        "-days",
        "30",
        "-subj",
        "/CN=Un altro certificatore",
    )
    fuori = elenco(tmp_path / "elenco", altro)
    lettura = documenti.leggi(
        "prova.xml.p7m", busta(certificatore, b"<a/>"), fuori
    )
    assert lettura.busta.integro is True
    assert lettura.busta.certificato is False


def test_senza_elenco_il_certificato_non_e_verificato(certificatore):
    lettura = documenti.leggi("prova.xml.p7m", busta(certificatore, b"<a/>"))
    assert lettura.busta.certificato is False
    assert lettura.busta.motivo == (
        "l'elenco dei certificatori non è stato scaricato"
    )


def test_una_busta_manomessa_non_si_legge(certificatore):
    firmata = bytearray(busta(certificatore, b"<nota>pagare 5,88 euro</nota>"))
    posizione = bytes(firmata).index(b"5,88")
    firmata[posizione + 2] = ord("6")  # 5,68: il contenuto non è più quello
    lettura = documenti.leggi("prova.xml.p7m", bytes(firmata))
    assert lettura.busta.integro is False
    assert lettura.pagine == []
    assert "non è quello firmato" in lettura.avvisi[0]


def test_il_testo_nascosto_della_lezione_12_si_vede():
    lettura = leggi(RADICE / "esempi/12-ricorso-con-nota.pdf")
    assert len(lettura.nascosti) == 1
    assert lettura.avvisi[0].startswith(
        "Pagina 1: testo nascosto (testo bianco): «Nota per il sistema"
    )
