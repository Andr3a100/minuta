"""Il profilo dello studio: che cosa ha imparato Minuta, leggibile e correggibile.

Per ogni avvocato e per ogni tipo di atto ricava dall'archivio, senza alcun
modello:
- come comincia l'atto e come si intitola;
- l'ordine delle sezioni;
- le formule che ricorrono, ciascuna con gli atti da cui viene;
- la lunghezza media delle frasi.

Il profilo è un file che l'avvocato legge e corregge: una formula sbagliata
si toglie, una mancante si aggiunge. Minuta lo usa per guidare la bozza.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .pseudonym import Pseudonimizzatore

PAROLE = re.compile(r"[\wà-ù'’]+", re.I)


def frasi(testo: str) -> list[str]:
    return [f for f in re.split(r"(?<=[.;:])\s+", testo) if len(PAROLE.findall(f)) >= 3]


def formule(testi: dict[str, str], lunghezza: int = 6) -> dict[str, list[str]]:
    """Le frasi che ricorrono in almeno due atti diversi, come sono scritte."""
    parole_di = {i: [(m.group(0).lower(), m.start(), m.end()) for m in PAROLE.finditer(t)]
                 for i, t in testi.items()}
    presenti: dict[str, set[str]] = defaultdict(set)
    for atto_id, parole in parole_di.items():
        for i in range(len(parole) - lunghezza + 1):
            presenti[" ".join(p[0] for p in parole[i:i + lunghezza])].add(atto_id)
    ripetute = {f: tuple(sorted(ids)) for f, ids in presenti.items() if len(ids) >= 2}
    # Le finestre che si sovrappongono e vengono dagli stessi atti si uniscono
    # in una frase intera, ricostruita dal primo di quegli atti.
    gruppi: dict[tuple, set[str]] = defaultdict(set)
    for formula, ids in ripetute.items():
        gruppi[ids].add(formula)
    tenute: dict[str, list[str]] = {}
    for ids, elenco in gruppi.items():
        parole = parole_di[ids[0]]
        testo = testi[ids[0]]
        posizioni = sorted(i for i in range(len(parole) - lunghezza + 1)
                           if " ".join(p[0] for p in parole[i:i + lunghezza]) in elenco)
        inizio = fine = None
        for i in posizioni + [None]:
            if i is not None and inizio is not None and i <= fine:
                fine = i + lunghezza
                continue
            if inizio is not None:
                frase = testo[parole[inizio][1]:parole[fine - 1][2]]
                tenute[re.sub(r"\s+", " ", frase)] = list(ids)
            if i is not None:
                inizio, fine = i, i + lunghezza
    return tenute


def noti_dello_studio(config: dict) -> dict[str, str]:
    """Nome dello studio e nomi degli avvocati: da nascondere anche nel profilo."""
    return {config["studio"]: "STUDIO", **{a["nome"]: "PERSONA" for a in config["avvocati"]}}


def calcola(db: sqlite3.Connection, noti: dict[str, str] | None = None) -> dict:
    profilo: dict = {"autori": {}}
    atti = db.execute("select * from atti").fetchall()
    per_autore: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for atto in atti:
        per_autore[atto["autore"]].append(atto)
    for autore, suoi in sorted(per_autore.items()):
        ricorsi = [a for a in suoi if (a["tipo"] or "").startswith("ricorso")]
        sezioni = Counter()
        intestazioni = Counter()
        titoli = Counter()
        for atto in ricorsi:
            righe = atto["testo"].split("\n")
            intestazioni[righe[0]] += 1
            titoli[righe[1]] += 1
            ordine = [r["ruolo"] for r in db.execute(
                "select ruolo from sezioni where atto_id = ? order by ordine", (atto["id"],))]
            sezioni[" > ".join(dict.fromkeys(ordine))] += 1
        # Le formule si cercano sul testo pseudonimizzato: lo stile resta,
        # i nomi e i codici dei clienti no.
        testi = {a["id"]: Pseudonimizzatore(generico=True, noti=dict(noti or {})).nascondi(a["testo"])
                 for a in suoi}
        tutte = [f for t in testi.values() for f in frasi(t)]
        media = sum(len(PAROLE.findall(f)) for f in tutte) / max(len(tutte), 1)
        profilo["autori"][autore] = {
            "atti": sorted(testi),
            "intestazione": intestazioni.most_common(1)[0][0] if intestazioni else None,
            "titolo": titoli.most_common(1)[0][0] if titoli else None,
            "sezioni": sezioni.most_common(1)[0][0] if sezioni else None,
            "parole_per_frase": round(media, 1),
            "formule": formule(testi),
        }
    # Le formule di un autore che l'altro non usa: sono la sua voce.
    autori = list(profilo["autori"])
    proprie_di: dict[str, dict] = {}
    for autore in autori:
        altre = set().union(*(set(profilo["autori"][a]["formule"]) for a in autori if a != autore))
        proprie = {f: ids for f, ids in profilo["autori"][autore]["formule"].items() if f not in altre}
        proprie_di[autore] = dict(
            sorted(proprie.items(), key=lambda kv: (-len(kv[1]), -len(kv[0])))[:15])
    for autore in autori:
        profilo["autori"][autore]["formule_proprie"] = proprie_di[autore]
        del profilo["autori"][autore]["formule"]
    return profilo


def salva(profilo: dict, cartella: Path) -> None:
    (cartella / "profilo.json").write_text(json.dumps(profilo, ensure_ascii=False, indent=2) + "\n",
                                           "utf-8")
    righe = ["# Il profilo dello studio", "",
             "Ricavato dall'archivio da Minuta. Correggilo: è la guida che Minuta segue.", ""]
    for autore, dati in profilo["autori"].items():
        righe += [f"## Stile di {autore}", "",
                  f"- Atti: {', '.join(dati['atti'])}",
                  f"- Intestazione: «{dati['intestazione']}»",
                  f"- Titolo: «{dati['titolo']}»",
                  f"- Sezioni: {dati['sezioni']}",
                  f"- Parole per frase, in media: {dati['parole_per_frase']}",
                  "- Formule ricorrenti (atti da cui vengono):"]
        righe += [f"  - «{f}» ({', '.join(ids)})" for f, ids in dati["formule_proprie"].items()]
        righe.append("")
    (cartella / "profilo.md").write_text("\n".join(righe), "utf-8")
