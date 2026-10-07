"""Il fascicolo dalle fatture elettroniche.

Un ricorso per decreto ingiuntivo nasce quasi sempre da fatture non pagate, e
fra imprese le fatture sono file XML nel formato FatturaPA, spesso firmati
(.xml.p7m). Minuta ne legge le parti, i numeri, gli importi, le scadenze, i
documenti di trasporto e gli ordini, e prepara il fascicolo: un file JSON che
l'avvocato rilegge e completa. Ciò che le fatture non dicono (il giudice, la
diffida, il legale rappresentante) resta «da completare».

Formato: specifiche tecniche FatturaPA versione 1.4, in vigore dal 1° aprile
2025, schema 1.2.3 (fonti/fatturapa/, scaricato da fatturapa.gov.it il 6
ottobre 2026).

Dei file firmati Minuta estrae il contenuto con openssl, che controlla che il
contenuto corrisponda alla firma ma non verifica i certificati di chi ha
firmato: la validità della firma resta da controllare con gli strumenti dello
studio.
"""

from __future__ import annotations

import base64
import binascii
import subprocess
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from pathlib import Path

from .draft import data_it, euro

# I tipi di documento dello schema 1.2.3 che entrano nel credito. Gli altri
# (acconti, autofatture, integrazioni) si segnalano all'avvocato e restano fuori.
NEL_CREDITO = {"TD01": "fattura", "TD05": "nota di debito", "TD06": "parcella",
               "TD24": "fattura differita", "TD25": "fattura differita"}
NOTA_DI_CREDITO = "TD04"


def _contenuto(percorso: Path) -> bytes:
    dati = percorso.read_bytes()
    if percorso.suffix.lower() != ".p7m":
        return dati
    # Un .p7m arriva in binario (DER) o, a volte, trascritto in base64.
    prove = [dati]
    try:
        prove.append(base64.b64decode(dati, validate=False))
    except (binascii.Error, ValueError):
        pass
    for prova in prove:
        uscita = subprocess.run(["openssl", "smime", "-verify", "-noverify", "-inform", "DER"],
                                input=prova, capture_output=True)
        if uscita.returncode == 0 and uscita.stdout.lstrip().startswith(b"<"):
            return uscita.stdout
    raise ValueError(f"{percorso.name}: non riesco ad aprire il file firmato")


def _senza_spazi_dei_nomi(radice):
    for elemento in radice.iter():
        if isinstance(elemento.tag, str) and "}" in elemento.tag:
            elemento.tag = elemento.tag.split("}", 1)[1]
    return radice


def _t(elemento, percorso: str) -> str | None:
    trovato = elemento.find(percorso) if elemento is not None else None
    return trovato.text.strip() if trovato is not None and trovato.text else None


def _soggetto(nodo) -> dict:
    anagrafici = nodo.find("DatiAnagrafici")
    anagrafica = anagrafici.find("Anagrafica")
    denominazione = _t(anagrafica, "Denominazione")
    nome = denominazione or " ".join(filter(None, (_t(anagrafica, "Nome"), _t(anagrafica, "Cognome"))))
    paese, codice = _t(anagrafici, "IdFiscaleIVA/IdPaese"), _t(anagrafici, "IdFiscaleIVA/IdCodice")
    sede = nodo.find("Sede")
    via = " ".join(filter(None, (_t(sede, "Indirizzo"), _t(sede, "NumeroCivico"))))
    comune, provincia, nazione = _t(sede, "Comune"), _t(sede, "Provincia"), _t(sede, "Nazione")
    luogo = f"{comune} ({provincia})" if provincia else comune
    soggetto = {"nome": nome,
                "piva": (codice if paese == "IT" else f"{paese}{codice}") if codice else "",
                "sede": f"{via}, {luogo}" + ("" if nazione in (None, "IT") else f", {nazione}")}
    if _t(anagrafici, "CodiceFiscale"):
        soggetto["cf"] = _t(anagrafici, "CodiceFiscale")
    if not denominazione:
        soggetto["persona_fisica"] = True
    return soggetto


def _documento(corpo) -> dict:
    generali = corpo.find("DatiGenerali/DatiGeneraliDocumento")
    totale = _t(generali, "ImportoTotaleDocumento")
    if totale is None:  # facoltativo nello schema: si ricava dal riepilogo IVA
        totale = sum((Decimal(_t(r, "ImponibileImporto") or "0") + Decimal(_t(r, "Imposta") or "0")
                      for r in corpo.findall("DatiBeniServizi/DatiRiepilogo")), Decimal("0"))
    pagamenti = corpo.findall("DatiPagamento/DettaglioPagamento")
    return {
        "tipo": _t(generali, "TipoDocumento"), "numero": _t(generali, "Numero"),
        "data": _t(generali, "Data"), "divisa": _t(generali, "Divisa"),
        "importo": float(Decimal(totale)),
        "da_pagare": (float(sum(Decimal(_t(p, "ImportoPagamento") or "0") for p in pagamenti))
                      if pagamenti else None),
        "scadenze": sorted({s for p in pagamenti if (s := _t(p, "DataScadenzaPagamento"))}),
        "ddt": [(_t(d, "NumeroDDT"), _t(d, "DataDDT")) for d in corpo.findall("DatiGenerali/DatiDDT")],
        "ordini": [(_t(o, "IdDocumento"), _t(o, "Data"))
                   for o in corpo.findall("DatiGenerali/DatiOrdineAcquisto")],
        "collegate": [_t(c, "IdDocumento") for c in corpo.findall("DatiGenerali/DatiFattureCollegate")],
        "descrizioni": [d.text.strip() for d in corpo.findall("DatiBeniServizi/DettaglioLinee/Descrizione")
                        if d.text],
        "causale": " ".join(c.text.strip() for c in generali.findall("Causale") if c.text),
    }


def leggi(percorso: Path) -> dict:
    """Un file FatturaPA: le parti e i documenti che contiene (un file può contenerne più d'uno)."""
    return leggi_dati(_contenuto(percorso), percorso.name)


def leggi_dati(dati: bytes, nome: str) -> dict:
    """Come leggi, dal contenuto già aperto (lezione 16)."""
    radice = _senza_spazi_dei_nomi(ET.fromstring(dati))
    if radice.tag != "FatturaElettronica":
        raise ValueError(f"{nome}: non è una fattura elettronica FatturaPA")
    testata = radice.find("FatturaElettronicaHeader")
    return {"file": nome,
            "cedente": _soggetto(testata.find("CedentePrestatore")),
            "cessionario": _soggetto(testata.find("CessionarioCommittente")),
            "documenti": [_documento(c) for c in radice.findall("FatturaElettronicaBody")]}


def _elenco(voci: list[str]) -> str:
    return voci[0] if len(voci) == 1 else ", ".join(voci[:-1]) + " e " + voci[-1]


def _chiave(soggetto: dict) -> str:
    return soggetto["piva"] or soggetto.get("cf") or soggetto["nome"]


def fascicolo(letti: list[dict], numero: str, avvocato: str, oggi: date) -> dict:
    """Il fascicolo per un ricorso per decreto ingiuntivo, con le avvertenze per l'avvocato."""
    if len({_chiave(f["cedente"]) for f in letti}) > 1 or len({_chiave(f["cessionario"]) for f in letti}) > 1:
        raise ValueError("le fatture non sono tutte fra le stesse parti: un fascicolo ha un creditore "
                         "e un debitore")
    cedente, cessionario = letti[0]["cedente"], letti[0]["cessionario"]
    avvertenze, fatture, note, documenti_letti = [], [], [], []
    for documento in (d for f in letti for d in f["documenti"]):
        voce = {"numero": documento["numero"], "data": documento["data"], "importo": documento["importo"]}
        if documento["scadenze"]:
            voce["scadenze"] = documento["scadenze"]
        nome = f"{NEL_CREDITO.get(documento['tipo'], 'documento')} n. {documento['numero']}"
        if documento["divisa"] != "EUR":
            avvertenze.append(f"{nome}: importi in {documento['divisa']}, non in euro.")
        if documento["tipo"] == NOTA_DI_CREDITO:
            note.append(voce)
            riferite = ", ".join(filter(None, documento["collegate"])) or "nessuna fattura indicata"
            avvertenze.append(f"nota di credito n. {documento['numero']} di euro "
                              f"{euro(documento['importo'])} (riferita a: {riferite}): tolta dal credito.")
            continue
        if documento["tipo"] not in NEL_CREDITO:
            avvertenze.append(f"documento n. {documento['numero']} di tipo {documento['tipo']}: "
                              "non entra nel credito, da valutare.")
            continue
        fatture.append(voce)
        documenti_letti.append(documento)
        if documento["da_pagare"] is not None and abs(documento["da_pagare"] - documento["importo"]) >= 0.01:
            avvertenze.append(f"{nome}: da pagare euro {euro(documento['da_pagare'])} su un totale di "
                              f"euro {euro(documento['importo'])} (ritenuta, scissione dei pagamenti, "
                              "acconti?): da verificare.")
        if not documento["scadenze"]:
            avvertenze.append(f"{nome}: la fattura non indica la scadenza.")
        elif max(documento["scadenze"]) >= oggi.isoformat():
            avvertenze.append(f"{nome}: scade il {data_it(max(documento['scadenze']))}, "
                              "non è ancora scaduta.")
    if not fatture:
        raise ValueError("nessuna fattura da cui nasca un credito")
    if not cessionario["piva"]:
        avvertenze.append("il debitore non ha partita IVA: potrebbe essere un consumatore. Verificare se "
                          "si applica il D.Lgs. 231/2002 e quale giudice è competente.")

    numeri = [f"n. {f['numero']}" for f in fatture]
    documenti = [f"fatture {_elenco(numeri)}" if len(numeri) > 1 else f"fattura {numeri[0]}"]
    if note:
        documenti.append("note di credito " + _elenco([f"n. {n['numero']}" for n in note]))
    ddt = [f"n. {n} del {data_it(d)}" for doc in documenti_letti for n, d in doc["ddt"] if n and d]
    if ddt:
        documenti.append(f"documenti di trasporto {_elenco(list(dict.fromkeys(ddt)))}")
    ordini = [f"n. {n}" + (f" del {data_it(d)}" if d else "") for doc in documenti_letti
              for n, d in doc["ordini"] if n]
    if ordini:
        documenti.append(f"ordini {_elenco(list(dict.fromkeys(ordini)))}")
    documenti.append("[DA COMPLETARE: altri documenti da produrre]")
    # Il rapporto fra le parti: una proposta dalle causali o dalle descrizioni,
    # che l'avvocato riscrive se serve.
    descrizioni = [d["causale"] or "; ".join(d["descrizioni"][:2]) for d in documenti_letti]
    rapporto = "; ".join(dict.fromkeys(filter(None, descrizioni))) or "[DA COMPLETARE: il rapporto fra le parti]"
    avvertenze.append("rapporto fra le parti ricavato dalle fatture: rileggilo nel fascicolo.")

    risultato = {
        "id": numero, "tipo": "ricorso decreto ingiuntivo",
        "giudice": "[DA COMPLETARE: giudice competente]", "stile": avvocato,
        "ricorrente": {**cedente, "rappresentante": ""}, "intimata": cessionario,
        "rapporto": rapporto, "fatture": fatture,
        "diffida": None,
        "interessi": "commerciali" if cessionario["piva"] else "da verificare",
        "documenti": documenti,
        "dalle_fatture": {"file": [f["file"] for f in letti], "letti_il": oggi.isoformat()},
        "avvertenze": avvertenze,
    }
    if note:
        risultato["note_di_credito"] = note
    return risultato
