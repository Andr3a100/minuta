"""Costruisce il massimario dello studio dalle citazioni dell'archivio.

    .venv/bin/python strumenti/verifica_massimario.py

Ogni norma citata negli atti viene aperta sul testo vigente di Normattiva.
Le sentenze restano «da verificare» finché un avvocato non le controlla
sulla fonte e le segna verificate. Scrive config/massimario.json e un
verbale datato in verbali/.
"""

import time
from collections import Counter
from datetime import date
from pathlib import Path

from minuta import archive, citations

RADICE = Path(__file__).resolve().parents[1]

config = archive.carica_config(RADICE / "config/studio.json")
uso: Counter = Counter()
prime: dict = {}
for pdf in sorted((RADICE / "archivio/pdf").glob("*.pdf")):
    atto = archive.leggi_atto(pdf, config["avvocati"])
    for citazione in citations.estrai(atto.testo):
        uso[citazione.chiave] += 1
        prime.setdefault(citazione.chiave, (citazione, atto.id))

massimario = citations.Massimario(RADICE / "config/massimario.json")
righe = [f"Verifica del massimario · {date.today().isoformat()} · {len(uso)} citazioni"]
for chiave in sorted(uso):
    citazione, atto_id = prime[chiave]
    if citazione.tipo == "norma":
        esito = citations.verifica_su_normattiva(chiave)
        time.sleep(1)
    else:
        esito = {"chiave": chiave, "stato": "da verificare",
                 "motivo": "sentenza: va controllata da un avvocato sulla fonte"}
    massimario.voci[chiave] = {**esito, "tipo": citazione.tipo, "usata_negli_atti": uso[chiave],
                               "esempio": citazione.testo, "primo_atto": atto_id}
    righe.append(f"{esito['stato']:<14} {chiave:<26} {uso[chiave]:>2} atti  "
                 f"{esito.get('motivo', esito.get('indirizzo', ''))}")
massimario.salva()
verbale = RADICE / f"verbali/massimario-{date.today().isoformat()}.txt"
verbale.write_text("\n".join(righe) + "\n", "utf-8")
print("\n".join(righe))
