"""I dati essenziali di una fattura elettronica FatturaPA: lezione B8.

    python fattura.py fattura.xml
"""

import sys
import xml.etree.ElementTree as ET


def trova(nodo, percorso):
    """Il testo di un elemento, qualunque sia lo spazio dei nomi."""
    for parte in percorso.split("/"):
        nodo = next(
            e for e in nodo.iter() if e.tag.rsplit("}", 1)[-1] == parte
        )
    return nodo.text


radice = ET.parse(sys.argv[1]).getroot()
print("Fornitore:", trova(radice, "CedentePrestatore/Denominazione"))
print("Cliente:  ", trova(radice, "CessionarioCommittente/Denominazione"))
print("Numero:   ", trova(radice, "DatiGeneraliDocumento/Numero"))
print("Data:     ", trova(radice, "DatiGeneraliDocumento/Data"))
print("Totale:   ", trova(radice, "ImportoTotaleDocumento"), "euro")
print("Scadenza: ", trova(radice, "DataScadenzaPagamento"))
