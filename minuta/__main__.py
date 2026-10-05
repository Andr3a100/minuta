"""I comandi di Minuta.

    python -m minuta importa
    python -m minuta cerca "riconoscimento di debito" --autore sarti
    python -m minuta profilo
    python -m minuta bozza tests/fascicolo-prova.json --modello finto
    python -m minuta esempio 06 --no --motivo "interessi generici"
    python -m minuta approva bozze/2026-041-....md --finale firmato.pdf --avvocato sarti \
        --fascicolo tests/fascicolo-prova.json
    python -m minuta correzioni --avvocato sarti
    python -m minuta dataset
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from . import archive, citations, draft, learning, model, profile, search
from .pseudonym import Pseudonimizzatore

RADICE = Path.cwd()


def main(argomenti: list[str] | None = None) -> int:
    lettore = argparse.ArgumentParser(prog="minuta", description="L'assistente dello studio.")
    comandi = lettore.add_subparsers(dest="comando", required=True)
    comandi.add_parser("importa", help="legge i PDF dell'archivio")
    cerca = comandi.add_parser("cerca", help="ritrova i precedenti")
    cerca.add_argument("domanda")
    cerca.add_argument("--tipo")
    cerca.add_argument("--autore")
    comandi.add_parser("profilo", help="ricava il profilo dello studio")
    bozza = comandi.add_parser("bozza", help="prepara una bozza da un fascicolo")
    bozza.add_argument("fascicolo", type=Path)
    bozza.add_argument("--modello", default=None, help="finto, anthropic, openai")
    bozza.add_argument("--uscita", type=Path, default=Path("bozze"))
    comandi.add_parser("dataset", help="esempi pseudonimizzati per l'addestramento (livello 2)")
    comandi.add_parser("modelli", help="i modelli disponibili sull'account OpenAI")
    esempio = comandi.add_parser("esempio", help="indica se un atto è un buon esempio")
    esempio.add_argument("atto")
    scelta = esempio.add_mutually_exclusive_group(required=True)
    scelta.add_argument("--si", action="store_true")
    scelta.add_argument("--no", action="store_true")
    esempio.add_argument("--motivo", default="")
    approva = comandi.add_parser("approva", help="registra l'atto firmato e impara dalle correzioni")
    approva.add_argument("bozza", type=Path)
    approva.add_argument("--finale", type=Path, required=True, help="l'atto firmato: .txt, .md o .pdf")
    approva.add_argument("--avvocato", required=True)
    approva.add_argument("--fascicolo", type=Path, required=True,
                         help="il fascicolo: i dati del cliente restano nascosti quando l'atto fa da esempio")
    correzioni = comandi.add_parser("correzioni", help="che cosa Minuta ha imparato dalle correzioni")
    correzioni.add_argument("--avvocato", help="solo le correzioni di questo avvocato")
    correzioni.add_argument("--respingi", type=int, metavar="N",
                            help="la correzione numero N non deve diventare regola")
    a = lettore.parse_args(argomenti)
    model.carica_env(RADICE / ".env")

    config = archive.carica_config(RADICE / "config/studio.json")
    db = archive.apri(RADICE / "minuta.db")

    if a.comando == "modelli":
        for nome in model.modelli_openai():
            print(nome)
        return 0
    curatela_file = RADICE / "config/curatela.json"
    correzioni_file = RADICE / "config/correzioni.json"
    if a.comando == "esempio":
        learning.segna_esempio(curatela_file, a.atto, a.si, a.motivo)
        print(f"atto {a.atto}: {'buon esempio' if a.si else 'non usarlo come esempio'}")
        return 0
    if a.comando == "correzioni":
        if a.respingi:
            if not a.avvocato:
                lettore.error("--respingi vuole anche --avvocato")
            try:
                voce = learning.respingi(correzioni_file, a.avvocato, a.respingi)
            except ValueError as errore:
                lettore.error(str(errore))
            print(f"respinta: «{voce['prima']}» → «{voce['dopo']}» non diventerà regola")
            return 0
        avvocati = [a.avvocato] if a.avvocato else [av["id"] for av in config["avvocati"]]
        for autore in avvocati:
            print(f"== {autore}")
            for n, v in enumerate(learning.voci_ordinate(correzioni_file, autore), start=1):
                stato = ("respinta" if v.get("respinta")
                         else "regola" if learning.e_regola(v) else "osservata")
                print(f"  {n}. [{stato}] «{v['prima']}» → «{v['dopo']}»  "
                      f"(in {learning.quanti(len(v['fascicoli']), 'atto', 'atti')}, "
                      f"{learning.quanti(v['volte'], 'volta', 'volte')})")
        return 0
    if a.comando == "approva":
        markdown = a.bozza.read_text("utf-8")
        fascicolo = json.loads(a.fascicolo.read_text("utf-8"))
        numero = fascicolo["id"]
        della_bozza = re.search(r"fascicolo (\S+) ·", markdown.split("\n", 1)[0])
        if della_bozza and della_bozza.group(1) != numero:
            lettore.error(f"la bozza è del fascicolo {della_bozza.group(1)}, non del {numero}")
        bozza = learning.testo_della_bozza(markdown)
        if a.finale.suffix == ".pdf":
            finale = learning.testo_firmato(archive.leggi_pdf(a.finale))
        else:
            finale = learning.testo_della_bozza(a.finale.read_text("utf-8"))
        riservati = draft.sensibili_del_fascicolo(fascicolo)
        noti = {**profile.noti_dello_studio(config), **riservati}
        modifiche = learning.confronta(bozza, finale, noti)
        learning.aggiorna_correzioni(correzioni_file, a.avvocato, numero, modifiche)
        learning.registra_approvazione(RADICE / "registro", numero, a.bozza.name, a.avvocato,
                                       modifiche, finale)
        scheda = archive.salva_approvato(RADICE / "archivio/approvati", finale, {
            "atto_id": numero, "autore": a.avvocato,
            "tipo": fascicolo.get("tipo", "ricorso decreto ingiuntivo"),
            "giudice": fascicolo.get("giudice"),
            "valore": sum(f["importo"] for f in fascicolo.get("fatture", [])) or None,
            "data": datetime.now().date().isoformat(), "riservati": riservati})
        archive.importa_approvato(scheda, db)
        conteggio = {t: sum(1 for m in modifiche if m["tipo"] == t) for t in learning.TIPI}
        q = learning.quanti
        print(f"approvata da {a.avvocato}: "
              f"{q(conteggio['completamento'], 'completamento', 'completamenti')}, "
              f"{q(conteggio['dati'], 'modifica di dati', 'modifiche di dati')}, "
              f"{q(conteggio['stile'], 'correzione di stile', 'correzioni di stile')}, "
              f"{q(conteggio['riscrittura'], 'riscrittura', 'riscritture')}")
        for m in modifiche:
            if m["tipo"] == "stile":
                print(f"  stile: «{m['prima']}» → «{m['dopo']}»")
        print(f"l'atto firmato è nell'archivio come {numero}")
        return 0
    if a.comando == "importa":
        atti = archive.importa(RADICE / "archivio/pdf", db, config)
        for atto in atti:
            print(f"{atto.id}  {atto.data}  {atto.autore or '?':6}  {atto.tipo}  "
                  f"{atto.giudice or '-'}  euro {atto.valore}")
        firmati = archive.importa_approvati(RADICE / "archivio/approvati", db)
        for atto in firmati:
            print(f"{atto.id}  {atto.data}  {atto.autore or '?':6}  {atto.tipo}  "
                  f"{atto.giudice or '-'}  euro {atto.valore}  (firmato, da archivio/approvati)")
        print(f"{len(atti) + len(firmati)} atti nell'archivio locale")
    elif a.comando == "cerca":
        for r in search.cerca(db, a.domanda, tipo=a.tipo, autore=a.autore):
            print(f"{r.atto_id}  {r.punteggio:7.3f}  {r.autore}  {r.data}  {r.estratto}")
    elif a.comando == "profilo":
        dati = profile.calcola(db, profile.noti_dello_studio(config))
        profile.salva(dati, RADICE / "config")
        print("config/profilo.md e config/profilo.json aggiornati")
    elif a.comando == "bozza":
        fascicolo = json.loads(a.fascicolo.read_text("utf-8"))
        profilo = json.loads((RADICE / "config/profilo.json").read_text("utf-8"))
        massimario = citations.Massimario(RADICE / "config/massimario.json")
        prezzi_file = RADICE / "config/prezzi.json"
        prezzi = json.loads(prezzi_file.read_text("utf-8")) if prezzi_file.exists() else {}
        risultato = draft.prepara(
            db, fascicolo, config, profilo, massimario, model.scegli(a.modello),
            RADICE / "registro", prezzi, curatela=learning.carica_curatela(curatela_file),
            apprese=learning.voci_regola(correzioni_file, fascicolo["stile"]))
        a.uscita.mkdir(parents=True, exist_ok=True)
        nome = f"{fascicolo['id']}-{datetime.now():%Y%m%d-%H%M%S}.md"
        (a.uscita / nome).write_text(draft.in_markdown(risultato, fascicolo), "utf-8")
        print(f"bozza in {a.uscita / nome}")
        for avviso in risultato.avvisi:
            print(f"  · {avviso}")
    elif a.comando == "dataset":
        # Livello 2: coppie richiesta-atto, pseudonimizzate, per addestrare un
        # modello. Prima di usarle serve la valutazione d'impatto: in cloud
        # significa mandare al fornitore l'intero archivio, non una richiesta.
        cartella = RADICE / "addestramento"
        cartella.mkdir(exist_ok=True)
        noti = profile.noti_dello_studio(config)
        # Gli avvocati diventano etichette neutre: lo stile si impara, il nome no.
        etichette = {av["id"]: f"stile {n}" for n, av in enumerate(config["avvocati"], start=1)}
        righe = []
        for riga in db.execute("select * from atti where tipo like 'ricorso%' order by id"):
            testo = Pseudonimizzatore(noti=dict(noti)).nascondi(riga["testo"])
            richiesta = (f"Scrivi un {riga['tipo']} davanti al {riga['giudice']}, "
                         f"nello {etichette.get(riga['autore'], 'stile dello studio')}, "
                         f"valore euro {riga['valore']}.")
            righe.append(json.dumps({"messages": [
                {"role": "user", "content": richiesta},
                {"role": "assistant", "content": testo}]}, ensure_ascii=False))
        (cartella / "esempi.jsonl").write_text("\n".join(righe) + "\n", "utf-8")
        print(f"{len(righe)} esempi in addestramento/esempi.jsonl (pseudonimizzati)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
