"""L'elenco dei certificatori qualificati: chi può emettere una firma digitale.

AgID pubblica l'elenco di fiducia italiano previsto dal regolamento eIDAS:
i prestatori di servizi fiduciari e i certificati dei loro servizi. Minuta
ne tiene i servizi che emettono certificati qualificati (tipo «CA/QC»)
attivi alla data dell'elenco, e verifica le firme solo rispetto a quelli:
mai rispetto a un certificato portato dal documento stesso (lezione 16).

Minuta scarica l'elenco dal sito di AgID con una connessione cifrata, e di
questa si fida: la firma XML dell'elenco non la controlla.
"""

from __future__ import annotations

import json
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

ELENCO = "https://eidas.agid.gov.it/TL/TSL-IT.xml"
NS = {"t": "http://uri.etsi.org/02231/v2#"}
QUALIFICATO = "http://uri.etsi.org/TrstSvc/Svctype/CA/QC"
ATTIVO = "http://uri.etsi.org/TrstSvc/TrustedList/Svcstatus/granted"
CERTIFICATO = "t:ServiceDigitalIdentity/t:DigitalId/t:X509Certificate"
FILE_CERTIFICATI = "certificatori.pem"
FILE_NOTIZIE = "certificatori.json"


@dataclass
class Elenco:
    emesso: str  # data e ora dell'elenco, come le scrive AgID
    numero: int  # il numero progressivo dell'elenco
    servizi: int  # servizi qualificati attivi
    certificatori: int  # prestatori con almeno uno di quei servizi


def _pem(base64: str) -> str:
    righe = "".join(base64.split())
    corpo = "\n".join(righe[i : i + 64] for i in range(0, len(righe), 64))
    return f"-----BEGIN CERTIFICATE-----\n{corpo}\n-----END CERTIFICATE-----\n"


# [libro:elenco]
def leggi_elenco(xml: bytes) -> tuple[Elenco, list[str]]:
    """I certificati dei servizi qualificati attivi, e i dati dell'elenco."""
    radice = ET.fromstring(xml)
    schema = radice.find("t:SchemeInformation", NS)
    certificati, prestatori, servizi = [], set(), 0
    for prestatore in radice.iterfind(".//t:TrustServiceProvider", NS):
        nome = prestatore.findtext("t:TSPInformation/t:TSPName/t:Name", "", NS)
        for servizio in prestatore.iterfind(
            ".//t:TSPService/t:ServiceInformation", NS
        ):
            tipo = servizio.findtext("t:ServiceTypeIdentifier", "", NS)
            stato = servizio.findtext("t:ServiceStatus", "", NS)
            if tipo != QUALIFICATO or stato != ATTIVO:
                continue
            servizi += 1
            prestatori.add(nome)
            for certificato in servizio.iterfind(f".//{CERTIFICATO}", NS):
                certificati.append(_pem(certificato.text or ""))
    elenco = Elenco(
        emesso=schema.findtext("t:ListIssueDateTime", "", NS),
        numero=int(schema.findtext("t:TSLSequenceNumber", "0", NS)),
        servizi=servizi,
        certificatori=len(prestatori),
    )
    return elenco, certificati


# [/libro:elenco]


def scarica(cartella: Path, indirizzo: str = ELENCO) -> Elenco:
    """Scarica l'elenco e ne salva i certificati, per le verifiche."""
    with urllib.request.urlopen(indirizzo, timeout=60) as risposta:
        xml = risposta.read()
    elenco, certificati = leggi_elenco(xml)
    if not certificati:
        raise ValueError("L'elenco non contiene servizi qualificati attivi.")
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / FILE_CERTIFICATI).write_text("".join(certificati), "ascii")
    notizie = json.dumps(asdict(elenco), indent=2) + "\n"
    (cartella / FILE_NOTIZIE).write_text(notizie, "utf-8")
    return elenco


def notizie(cartella: Path) -> Elenco | None:
    """L'elenco salvato, o None se non è mai stato scaricato."""
    percorso = cartella / FILE_NOTIZIE
    if not percorso.is_file() or not (cartella / FILE_CERTIFICATI).is_file():
        return None
    return Elenco(**json.loads(percorso.read_text("utf-8")))
