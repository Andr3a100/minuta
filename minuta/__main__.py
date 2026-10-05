"""I comandi di Minuta.

    python -m minuta importa
    python -m minuta cerca "riconoscimento di debito" --autore sarti
    python -m minuta profilo
    python -m minuta bozza tests/fascicolo-prova.json --modello finto
    python -m minuta dataset
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import archive, citations, draft, model, profile, search
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
    a = lettore.parse_args(argomenti)
    model.carica_env(RADICE / ".env")

    config = archive.carica_config(RADICE / "config/studio.json")
    db = archive.apri(RADICE / "minuta.db")

    if a.comando == "modelli":
        for nome in model.modelli_openai():
            print(nome)
        return 0
    if a.comando == "importa":
        atti = archive.importa(RADICE / "archivio/pdf", db, config)
        for atto in atti:
            print(f"{atto.id}  {atto.data}  {atto.autore or '?':6}  {atto.tipo}  "
                  f"{atto.giudice or '-'}  euro {atto.valore}")
        print(f"{len(atti)} atti nell'archivio locale")
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
        risultato = draft.prepara(db, fascicolo, config, profilo, massimario,
                                  model.scegli(a.modello), RADICE / "registro", prezzi)
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
