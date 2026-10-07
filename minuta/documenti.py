"""I documenti del fascicolo: che cosa sono, che cosa dicono, come sono
stati letti (lezione 16).

Minuta riconosce un documento dal contenuto, non dal nome (lezione B1), e di
ciascuno dice come l'ha letto: il testo di un PDF, la lettura ottica di una
scansione, un file Word, una fattura elettronica, una busta firmata. La
lettura ottica produce una trascrizione, da controllare sull'immagine. Ogni
PDF passa dal controllo del testo nascosto (lezione 12).

Di una busta firmata Minuta dice due cose separate: se il documento è
integro, cioè uguale a quello che è stato firmato, e se il certificato di
chi ha firmato è stato emesso da un certificatore dell'elenco di AgID
(minuta/certificatori.py). Revoca e sospensione del certificato non le
controlla.
"""

from __future__ import annotations

import base64
import binascii
import functools
import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import docx
import pymupdf
from docx.table import Table

from . import certificatori, fatture, nascosti
from .draft import euro

TESSDATA = Path(__file__).resolve().parents[1] / "tessdata"
# Tesseract, il motore della lettura ottica, lavora meglio da 300 punti per
# pollice in su (tessdoc, «Improving the quality of the output»).
RISOLUZIONE_MINIMA = 300
TIPI = {
    "pdf": "PDF",
    "word": "Word",
    "fattura": "fattura elettronica",
    "xml": "XML",
    "busta": "busta firmata",
    "sconosciuto": "formato sconosciuto",
}
ESTENSIONI = {".pdf": "pdf", ".docx": "word", ".xml": "xml", ".p7m": "busta"}
GIT_WINDOWS = Path("C:/Program Files/Git/usr/bin/openssl.exe")
# Aprire la busta: -noverify controlla solo che il documento sia quello
# firmato. Verificare il certificato: rispetto ai soli certificatori
# dell'elenco, per qualunque uso (-purpose any).
APRI = ["smime", "-verify", "-noverify", "-binary", "-inform", "DER"]
VERIFICA = ["smime", "-verify", "-binary", "-inform", "DER", "-purpose", "any"]
MESI = (
    "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre "
    "ottobre novembre dicembre"
).split()


class DocumentoNonLeggibile(Exception):
    """Il documento non si può leggere: il messaggio dice perché."""


@dataclass
class Pagina:
    numero: int
    testo: str
    ottica: bool = False  # letta con la lettura ottica: è una trascrizione
    risoluzione: int | None = None  # punti per pollice della scansione


@dataclass
class Busta:
    integro: bool  # il documento è quello che è stato firmato
    firmatario: str  # il nome nel certificato di chi ha firmato
    certificato: bool  # emesso da un certificatore dell'elenco di AgID
    motivo: str  # perché il certificato è, o non è, verificato


@dataclass
class Lettura:
    nome: str
    tipo: str
    pagine: list[Pagina] = field(default_factory=list)
    nascosti: list[nascosti.Nascosto] = field(default_factory=list)
    busta: Busta | None = None
    avvisi: list[str] = field(default_factory=list)

    @property
    def testo(self) -> str:
        return "\n\n".join(p.testo for p in self.pagine if p.testo)

    @property
    def ottica(self) -> bool:
        return any(p.ottica for p in self.pagine)


# [libro:riconosci]
def riconosci(dati: bytes) -> str:
    """Il tipo del documento, dai primi byte: il nome può mentire."""
    if dati.startswith(b"%PDF-"):
        return "pdf"
    if dati.startswith(b"PK\x03\x04"):  # un archivio zip, come i .docx
        try:
            with zipfile.ZipFile(io.BytesIO(dati)) as archivio:
                if "word/document.xml" in archivio.namelist():
                    return "word"
        except zipfile.BadZipFile:
            pass
        return "sconosciuto"
    if dati.lstrip()[:1] == b"<":
        return "xml"
    if _der(dati) is not None:  # una busta firmata, in binario o in base64
        return "busta"
    return "sconosciuto"


# [/libro:riconosci]


def leggi(nome: str, dati: bytes, elenco: Path | None = None) -> Lettura:
    """Legge un documento; elenco è la cartella dei certificatori."""
    tipo = riconosci(dati)
    if tipo == "pdf":
        lettura = leggi_pdf(nome, dati)
    elif tipo == "word":
        lettura = leggi_word(nome, dati)
    elif tipo == "xml":
        lettura = leggi_xml(nome, dati)
    elif tipo == "busta":
        lettura = leggi_busta(nome, dati, elenco)
    else:
        lettura = Lettura(nome, TIPI["sconosciuto"])
        lettura.avvisi.append("Formato non riconosciuto: Minuta non lo legge.")
    estensione = Path(nome).suffix.lower()
    atteso = ESTENSIONI.get(estensione)
    if atteso and atteso != tipo:
        lettura.avvisi.insert(
            0,
            f"Il nome finisce in {estensione}, ma il contenuto è "
            f"{TIPI[tipo]}: Minuta l'ha letto come tale.",
        )
    return lettura


# ----------------------------------------------------------------------
# PDF, scansioni e lettura ottica
# ----------------------------------------------------------------------


def leggi_pdf(nome: str, dati: bytes) -> Lettura:
    lettura = Lettura(nome, TIPI["pdf"])
    try:
        documento = pymupdf.open(stream=dati, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError):
        lettura.avvisi.append("Il PDF è danneggiato: Minuta non lo legge.")
        return lettura
    with documento:
        if documento.needs_pass:
            lettura.avvisi.append("Il PDF è protetto da una password.")
            return lettura
        for numero, pagina in enumerate(documento, start=1):
            lettura.pagine.append(leggi_pagina(numero, pagina))
        lettura.nascosti = nascosti.nel_documento(documento)
    for pagina in lettura.pagine:
        if pagina.ottica:
            lettura.avvisi.append(avviso_ottica(pagina))
    for trovato in lettura.nascosti:
        lettura.avvisi.append(
            f"Pagina {trovato.pagina}: testo nascosto ({trovato.motivo}): "
            f"«{trovato.testo}»"
        )
    return lettura


# [libro:pagina]
def leggi_pagina(numero: int, pagina: pymupdf.Page) -> Pagina:
    """Il testo della pagina; se la pagina è solo un'immagine, la lettura
    ottica, sul computer dello studio."""
    testo = pagina.get_text().strip()
    if testo or not pagina.get_images():
        return Pagina(numero, testo)
    ocr = pagina.get_textpage_ocr(
        language="ita", dpi=300, full=True, tessdata=str(TESSDATA)
    )
    trascrizione = in_righe(pagina.get_text("words", textpage=ocr))
    return Pagina(numero, trascrizione, True, risoluzione(pagina))


def in_righe(parole: list) -> str:
    """Rimette in riga le parole lette: quelle alla stessa altezza."""
    righe: list[tuple[float, list]] = []
    for x0, y0, _x1, y1, parola, *_ in sorted(
        parole, key=lambda p: ((p[1] + p[3]) / 2, p[0])
    ):
        centro = (y0 + y1) / 2
        if righe and abs(righe[-1][0] - centro) < (y1 - y0) / 2:
            righe[-1][1].append((x0, parola))
        else:
            righe.append((centro, [(x0, parola)]))
    return "\n".join(" ".join(p for _, p in sorted(r)) for _, r in righe)


def risoluzione(pagina: pymupdf.Page) -> int | None:
    """I punti per pollice dell'immagine più grande della pagina."""
    immagini = pagina.get_image_info()
    if not immagini:
        return None
    grande = max(immagini, key=lambda i: i["width"] * i["height"])
    pollici = pymupdf.Rect(grande["bbox"]).width / 72
    return round(grande["width"] / pollici) if pollici else None


def avviso_ottica(pagina: Pagina) -> str:
    avviso = (
        f"Pagina {pagina.numero}: lettura ottica, una trascrizione da "
        "controllare sull'immagine"
    )
    if pagina.risoluzione and pagina.risoluzione < RISOLUZIONE_MINIMA:
        avviso += (
            f"; la scansione ha {pagina.risoluzione} punti per pollice, "
            f"meno dei {RISOLUZIONE_MINIMA} consigliati"
        )
    return avviso + "."


# [/libro:pagina]


# ----------------------------------------------------------------------
# Word e fatture elettroniche
# ----------------------------------------------------------------------


def leggi_word(nome: str, dati: bytes) -> Lettura:
    """Paragrafi e tabelle, nell'ordine del documento."""
    documento = docx.Document(io.BytesIO(dati))
    righe = []
    for parte in documento.iter_inner_content():
        if isinstance(parte, Table):
            for riga in parte.rows:
                righe.append(" | ".join(c.text.strip() for c in riga.cells))
        elif parte.text.strip():
            righe.append(parte.text.strip())
    return Lettura(nome, TIPI["word"], [Pagina(1, "\n".join(righe))])


def leggi_xml(nome: str, dati: bytes) -> Lettura:
    try:
        fattura = fatture.leggi_dati(dati, nome)
    except (ValueError, AttributeError, SyntaxError):  # SyntaxError: XML rotto
        lettura = Lettura(nome, TIPI["xml"])
        lettura.pagine.append(Pagina(1, dati.decode("utf-8", "replace")))
        lettura.avvisi.append(
            "Un file XML che non è una fattura elettronica FatturaPA: "
            "Minuta ne tiene il testo così com'è."
        )
        return lettura
    return Lettura(nome, TIPI["fattura"], [Pagina(1, riassunto(fattura))])


def riassunto(fattura: dict) -> str:
    """Le notizie essenziali della fattura, da leggere."""
    righe = [
        f"Fornitore: {_parte(fattura['cedente'])}",
        f"Cliente: {_parte(fattura['cessionario'])}",
    ]
    for documento in fattura["documenti"]:
        riga = (
            f"Fattura n. {documento['numero']} del "
            f"{_giorno(documento['data'])}: {euro(documento['importo'])} euro"
        )
        for scadenza in documento["scadenze"]:
            riga += f"; scadenza {_giorno(scadenza)}"
        righe.append(riga + ".")
        righe += documento["descrizioni"]
    return "\n".join(righe)


def _giorno(iso: str) -> str:
    anno, mese, giorno = (int(n) for n in iso.split("-"))
    return f"{giorno} {MESI[mese - 1]} {anno}"


def _parte(soggetto: dict) -> str:
    if soggetto.get("piva"):
        return f"{soggetto['nome']} (partita IVA {soggetto['piva']})"
    return soggetto["nome"]


# ----------------------------------------------------------------------
# Buste firmate (.p7m): integrità e certificato, separati
# ----------------------------------------------------------------------


def _der(dati: bytes) -> bytes | None:
    """La busta in binario (DER), anche se è arrivata in base64."""
    if dati[:1] == b"\x30":
        return dati
    if re.fullmatch(rb"[A-Za-z0-9+/=\s]+", dati[:4096] or b"-"):
        try:
            decodificati = base64.b64decode(dati, validate=False)
        except (binascii.Error, ValueError):
            return None
        if decodificati[:1] == b"\x30":
            return decodificati
    return None


@functools.cache
def openssl() -> list[str]:
    """Il comando openssl: su Windows quello di Git, se manca dal PATH."""
    trovato = shutil.which("openssl")
    if trovato is None and GIT_WINDOWS.is_file():
        trovato = str(GIT_WINDOWS)
    if trovato is None:
        raise DocumentoNonLeggibile(
            "openssl non si trova: serve per aprire le buste firmate "
            "(lezione B8)."
        )
    return [trovato]


@functools.cache
def _versione() -> str:
    """La prima riga di openssl version: OpenSSL 3, OpenSSL 1.1, LibreSSL."""
    uscita = subprocess.run(
        [*openssl(), "version"], capture_output=True, text=True
    )
    return uscita.stdout.strip()


def _solo_elenco(vuota: Path) -> list[str]:
    """Le opzioni che escludono i certificati di sistema dalla verifica.

    openssl aggiunge da solo i certificati del sistema, quelli dei siti
    web: qui contano solo i certificatori dell'elenco. OpenSSL 3 ha due
    raccolte di sistema da escludere, OpenSSL 1.1 una; LibreSSL non ha le
    opzioni -no-, e le basta una cartella di certificati vuota.
    """
    versione = _versione()
    if versione.startswith("LibreSSL"):
        return ["-CApath", str(vuota)]
    if versione.startswith("OpenSSL 1."):
        return ["-no-CApath"]
    return ["-no-CApath", "-no-CAstore"]


def _esegui(argomenti: list[str], dati: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*openssl(), *argomenti], input=dati, capture_output=True
    )


# [libro:busta]
def leggi_busta(nome: str, dati: bytes, elenco: Path | None) -> Lettura:
    """Apre la busta e dice, separate, integrità e certificato."""
    der = _der(dati)
    with tempfile.TemporaryDirectory() as cartella:
        firmatari = Path(cartella) / "firmatari.pem"
        aperta = _esegui([*APRI, "-signer", str(firmatari)], der)
        if aperta.returncode != 0:
            lettura = Lettura(nome, TIPI["busta"])
            lettura.busta = Busta(False, "", False, "la busta non si apre")
            lettura.avvisi.append(
                "La busta non si apre: il documento non è quello firmato, "
                "o la busta è danneggiata. Minuta non ne legge il contenuto."
            )
            return lettura
        firmatario = _nome_nel_certificato(firmatari.read_bytes())
    interno = nome[:-4] if nome.lower().endswith(".p7m") else nome
    lettura = leggi(interno, aperta.stdout, elenco)
    lettura.nome = nome
    lettura.tipo = f"{TIPI['busta']} con {lettura.tipo}"
    verificato, motivo = verifica_certificato(der, elenco)
    lettura.busta = Busta(True, firmatario, verificato, motivo)
    return lettura


def verifica_certificato(der: bytes, elenco: Path | None) -> tuple[bool, str]:
    """Il certificato di chi ha firmato viene da un certificatore
    dell'elenco di AgID? Revoca e sospensione restano fuori."""
    if elenco is None or certificatori.notizie(elenco) is None:
        return False, "l'elenco dei certificatori non è stato scaricato"
    pem = str(elenco / certificatori.FILE_CERTIFICATI)
    with tempfile.TemporaryDirectory() as vuota:
        solo = _solo_elenco(Path(vuota))
        verifica = _esegui([*VERIFICA, "-CAfile", pem, *solo], der)
    if verifica.returncode == 0:
        return True, "emesso da un certificatore dell'elenco di AgID"
    errore = verifica.stderr.decode("utf-8", "replace")
    if re.search(r"self[- ]signed", errore):
        return False, "firmato da sé stesso, non da un certificatore"
    if "unable to get local issuer certificate" in errore:
        return False, "chi l'ha emesso non è nell'elenco di AgID"
    if "expired" in errore:
        return False, "il certificato è scaduto"
    return False, "la verifica non è riuscita"


# [/libro:busta]


def _nome_nel_certificato(pem: bytes) -> str:
    """Il nome comune (CN) del primo certificato, come lo scrive openssl."""
    uscita = _esegui(["x509", "-noout", "-subject"], pem)
    soggetto = uscita.stdout.decode("utf-8", "replace")
    trovato = re.search(
        r"CN ?= ?(.+?)(?:, [A-Za-z]+ ?=|/[A-Za-z]+=|$)", soggetto.strip()
    )
    return trovato.group(1).strip() if trovato else soggetto.strip()
