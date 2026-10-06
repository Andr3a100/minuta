"""Le fatture elettroniche del caso di prova, nel formato FatturaPA.

    .venv/bin/python strumenti/genera_fatture.py

Scrive in archivio/fatture/ le due fatture del fascicolo di prova 2026-041,
di Officine Grafiche Taddei S.r.l. a Hotel Belvedere Sestola S.r.l. Società,
partite IVA, ordini e documenti di trasporto sono inventati. Ogni fattura si
convalida sullo schema ufficiale 1.2.3 (fonti/fatturapa/) prima di essere
scritta.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from lxml import etree

RADICE = Path(__file__).resolve().parents[1]
NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
SCHEMA = RADICE / "fonti/fatturapa/Schema_VFPR12_v1.2.3.xsd"
FIRME = RADICE / "fonti/fatturapa/xmldsig-core-schema.xsd"

CEDENTE = {"denominazione": "Officine Grafiche Taddei S.r.l.", "piva": "03555440361",
           "indirizzo": "Via delle Rotative", "civico": "3", "cap": "41122", "comune": "Modena",
           "provincia": "MO"}
CESSIONARIO = {"denominazione": "Hotel Belvedere Sestola S.r.l.", "piva": "02888990364",
               "indirizzo": "Via del Cimone", "civico": "21", "cap": "41029", "comune": "Sestola",
               "provincia": "MO"}
FATTURE = [
    {"numero": "455/2025", "data": "2025-11-14", "totale": "6840.00", "scadenza": "2025-12-14",
     "descrizione": "Stampa cataloghi stagione invernale 2025/2026",
     "ordine": ("33/2025", "2025-10-02"), "ddt": ("112", "2025-11-10")},
    {"numero": "489/2025", "data": "2025-12-05", "totale": "3120.50", "scadenza": "2026-01-04",
     "descrizione": "Stampa materiale promozionale stagione invernale 2025/2026",
     "ordine": ("38/2025", "2025-11-05"), "ddt": ("127", "2025-12-02")},
]


def _sotto(padre, nome: str, testo: str | None = None):
    elemento = ET.SubElement(padre, nome)
    if testo is not None:
        elemento.text = testo
    return elemento


def _soggetto(padre, nome: str, dati: dict, cedente: bool) -> None:
    nodo = _sotto(padre, nome)
    anagrafici = _sotto(nodo, "DatiAnagrafici")
    if dati.get("piva"):
        iva = _sotto(anagrafici, "IdFiscaleIVA")
        _sotto(iva, "IdPaese", "IT")
        _sotto(iva, "IdCodice", dati["piva"])
    if dati.get("cf"):
        _sotto(anagrafici, "CodiceFiscale", dati["cf"])
    anagrafica = _sotto(anagrafici, "Anagrafica")
    if dati.get("denominazione"):
        _sotto(anagrafica, "Denominazione", dati["denominazione"])
    else:
        _sotto(anagrafica, "Nome", dati["nome"])
        _sotto(anagrafica, "Cognome", dati["cognome"])
    if cedente:
        _sotto(anagrafici, "RegimeFiscale", "RF01")
    sede = _sotto(nodo, "Sede")
    for campo, chiave in (("Indirizzo", "indirizzo"), ("NumeroCivico", "civico"), ("CAP", "cap"),
                          ("Comune", "comune"), ("Provincia", "provincia")):
        if dati.get(chiave):
            _sotto(sede, campo, dati[chiave])
    _sotto(sede, "Nazione", "IT")


def fattura(cedente: dict, cessionario: dict, documenti: list[dict], progressivo: str = "00001") -> bytes:
    """Un file FatturaPA (fattura ordinaria, FPR12) con uno o più documenti."""
    ET.register_namespace("p", NS)
    radice = ET.Element(f"{{{NS}}}FatturaElettronica", {"versione": "FPR12"})
    testata = _sotto(radice, "FatturaElettronicaHeader")
    trasmissione = _sotto(testata, "DatiTrasmissione")
    trasmittente = _sotto(trasmissione, "IdTrasmittente")
    _sotto(trasmittente, "IdPaese", "IT")
    _sotto(trasmittente, "IdCodice", cedente["piva"])
    _sotto(trasmissione, "ProgressivoInvio", progressivo)
    _sotto(trasmissione, "FormatoTrasmissione", "FPR12")
    _sotto(trasmissione, "CodiceDestinatario", "0000000")
    _soggetto(testata, "CedentePrestatore", cedente, cedente=True)
    _soggetto(testata, "CessionarioCommittente", cessionario, cedente=False)
    for documento in documenti:
        totale = Decimal(documento["totale"])
        imponibile = (totale / Decimal("1.22")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        corpo = _sotto(radice, "FatturaElettronicaBody")
        generali = _sotto(corpo, "DatiGenerali")
        dati = _sotto(generali, "DatiGeneraliDocumento")
        _sotto(dati, "TipoDocumento", documento.get("tipo", "TD01"))
        _sotto(dati, "Divisa", "EUR")
        _sotto(dati, "Data", documento["data"])
        _sotto(dati, "Numero", documento["numero"])
        _sotto(dati, "ImportoTotaleDocumento", f"{totale:.2f}")
        _sotto(dati, "Causale", documento["descrizione"])
        if documento.get("ordine"):
            ordine = _sotto(generali, "DatiOrdineAcquisto")
            _sotto(ordine, "IdDocumento", documento["ordine"][0])
            _sotto(ordine, "Data", documento["ordine"][1])
        if documento.get("collegata"):
            collegata = _sotto(generali, "DatiFattureCollegate")
            _sotto(collegata, "IdDocumento", documento["collegata"])
        if documento.get("ddt"):
            ddt = _sotto(generali, "DatiDDT")
            _sotto(ddt, "NumeroDDT", documento["ddt"][0])
            _sotto(ddt, "DataDDT", documento["ddt"][1])
        servizi = _sotto(corpo, "DatiBeniServizi")
        linea = _sotto(servizi, "DettaglioLinee")
        _sotto(linea, "NumeroLinea", "1")
        _sotto(linea, "Descrizione", documento["descrizione"])
        _sotto(linea, "Quantita", "1.00")
        _sotto(linea, "PrezzoUnitario", f"{imponibile:.2f}")
        _sotto(linea, "PrezzoTotale", f"{imponibile:.2f}")
        _sotto(linea, "AliquotaIVA", "22.00")
        riepilogo = _sotto(servizi, "DatiRiepilogo")
        _sotto(riepilogo, "AliquotaIVA", "22.00")
        _sotto(riepilogo, "ImponibileImporto", f"{imponibile:.2f}")
        _sotto(riepilogo, "Imposta", f"{totale - imponibile:.2f}")
        _sotto(riepilogo, "EsigibilitaIVA", "I")
        pagamento = _sotto(corpo, "DatiPagamento")
        _sotto(pagamento, "CondizioniPagamento", "TP02")
        dettaglio = _sotto(pagamento, "DettaglioPagamento")
        _sotto(dettaglio, "ModalitaPagamento", "MP05")
        if documento.get("scadenza"):
            _sotto(dettaglio, "DataScadenzaPagamento", documento["scadenza"])
        _sotto(dettaglio, "ImportoPagamento", f"{Decimal(documento.get('da_pagare', totale)):.2f}")
    return ET.tostring(radice, encoding="utf-8", xml_declaration=True)


class _FirmeInLocale(etree.Resolver):
    """Lo schema importa quello delle firme del W3C: si legge dalla copia locale."""

    def resolve(self, url, pubblico, contesto):
        if url.endswith("xmldsig-core-schema.xsd"):
            return self.resolve_filename(str(FIRME), contesto)
        return None


def valida(xml: bytes) -> None:
    """Solleva un errore se il file non rispetta lo schema ufficiale FatturaPA 1.2.3."""
    lettore = etree.XMLParser()
    lettore.resolvers.add(_FirmeInLocale())
    etree.XMLSchema(etree.parse(str(SCHEMA), lettore)).assertValid(etree.fromstring(xml))


def main() -> None:
    cartella = RADICE / "archivio/fatture"
    cartella.mkdir(parents=True, exist_ok=True)
    for documento in FATTURE:
        progressivo = documento["numero"].split("/")[0].zfill(5)
        xml = fattura(CEDENTE, CESSIONARIO, [documento], progressivo)
        valida(xml)
        percorso = cartella / f"IT{CEDENTE['piva']}_{progressivo}.xml"
        percorso.write_bytes(xml)
        print(f"{percorso.relative_to(RADICE)}: fattura n. {documento['numero']}, valida (schema 1.2.3)")


if __name__ == "__main__":
    main()
