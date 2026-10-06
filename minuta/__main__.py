"""I comandi di Minuta.

    python -m minuta importa
    python -m minuta cerca "riconoscimento di debito" --autore sarti
    python -m minuta profilo
    python -m minuta fascicolo archivio/fatture/*.xml --numero 2026-041 --avvocato sarti
    python -m minuta bozza tests/fascicolo-prova.json --modello finto
    python -m minuta word bozze/2026-041-....md
    python -m minuta esempio 06 --no --motivo "interessi generici"
    python -m minuta approva bozze/2026-041-....docx --finale firmato.docx --avvocato sarti \
        --fascicolo tests/fascicolo-prova.json
    python -m minuta correzioni --avvocato sarti
    python -m minuta dataset
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from . import archive, citations, draft, fatture, learning, model, profile, search, word
from .pseudonym import Pseudonimizzatore

RADICE = Path.cwd()


def carta_intestata(avvocato: str) -> Path | None:
    """La carta intestata dell'avvocato, o quella dello studio, se c'è."""
    for nome in (f"carta-{avvocato}.docx", "carta-intestata.docx"):
        if (RADICE / "config" / nome).exists():
            return RADICE / "config" / nome
    return None


def main(argomenti: list[str] | None = None) -> int:
    lettore = argparse.ArgumentParser(prog="minuta", description="L'assistente dello studio.")
    comandi = lettore.add_subparsers(dest="comando", required=True)
    comandi.add_parser("importa", help="legge i PDF dell'archivio")
    cerca = comandi.add_parser("cerca", help="ritrova i precedenti")
    cerca.add_argument("domanda")
    cerca.add_argument("--tipo")
    cerca.add_argument("--autore")
    comandi.add_parser("profilo", help="ricava il profilo dello studio")
    dalle_fatture = comandi.add_parser("fascicolo",
                                       help="prepara il fascicolo dalle fatture elettroniche (FatturaPA)")
    dalle_fatture.add_argument("fatture", type=Path, nargs="+", help="file .xml o .xml.p7m")
    dalle_fatture.add_argument("--numero", required=True, help="il numero del fascicolo, per esempio 2026-041")
    dalle_fatture.add_argument("--avvocato", required=True)
    dalle_fatture.add_argument("--uscita", type=Path, help="predefinito: fascicoli/<numero>.json")
    bozza = comandi.add_parser("bozza", help="prepara una bozza da un fascicolo")
    bozza.add_argument("fascicolo", type=Path)
    bozza.add_argument("--modello", default=None, help="finto, anthropic, openai")
    bozza.add_argument("--uscita", type=Path, default=Path("bozze"))
    in_word = comandi.add_parser("word", help="una bozza già preparata, come file Word (.docx)")
    in_word.add_argument("bozza", type=Path)
    comandi.add_parser("dataset", help="esempi pseudonimizzati per l'addestramento (livello 2)")
    comandi.add_parser("modelli", help="i modelli disponibili sull'account OpenAI")
    esempio = comandi.add_parser("esempio", help="indica se un atto è un buon esempio")
    esempio.add_argument("atto")
    scelta = esempio.add_mutually_exclusive_group(required=True)
    scelta.add_argument("--si", action="store_true")
    scelta.add_argument("--no", action="store_true")
    esempio.add_argument("--motivo", default="")
    approva = comandi.add_parser("approva", help="registra l'atto firmato e impara dalle correzioni")
    approva.add_argument("bozza", type=Path, help="la bozza di Minuta: il file .md o il suo .docx")
    approva.add_argument("--finale", type=Path, required=True,
                         help="l'atto firmato: .docx, .pdf, .txt o .md")
    approva.add_argument("--comunque", action="store_true",
                         help="registra anche un atto in cui restano parti della bozza")
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
        # Il confronto si fa sempre con la bozza originale, salvata in Markdown:
        # il .docx l'avvocato può averlo corretto e salvato sopra.
        originale = a.bozza.with_suffix(".md")
        if not originale.exists():
            lettore.error(f"manca {originale}: serve la bozza originale per il confronto")
        markdown = originale.read_text("utf-8")
        fascicolo = json.loads(a.fascicolo.read_text("utf-8"))
        numero = fascicolo["id"]
        della_bozza = re.search(r"fascicolo (\S+) ·", markdown.split("\n", 1)[0])
        if della_bozza and della_bozza.group(1) != numero:
            lettore.error(f"la bozza è del fascicolo {della_bozza.group(1)}, non del {numero}")
        bozza = learning.testo_della_bozza(markdown)
        if a.finale.suffix == ".docx":
            finale = "\n\n".join(word.leggi(a.finale))
            residui = word.residui(a.finale)
        else:
            if a.finale.suffix == ".pdf":
                finale = learning.testo_firmato(archive.leggi_pdf(a.finale))
            else:
                finale = learning.testo_della_bozza(a.finale.read_text("utf-8"))
            residui = word.residui_nel_testo(finale)
        # Un atto in cui restano il riquadro, i commenti di Minuta o dati da
        # completare non è ancora l'atto firmato: non entra fra gli esempi.
        if residui and not a.comunque:
            lettore.error("l'atto sembra ancora una bozza (" + "; ".join(residui)
                          + "). Correggi il file e riprova, oppure aggiungi --comunque.")
        riservati = draft.sensibili_del_fascicolo(fascicolo)
        noti = {**profile.noti_dello_studio(config), **riservati}
        modifiche = learning.confronta(bozza, finale, noti)
        learning.aggiorna_correzioni(correzioni_file, a.avvocato, numero, modifiche)
        learning.registra_approvazione(RADICE / "registro", numero, originale.name, a.avvocato,
                                       modifiche, finale, residui)
        scheda = archive.salva_approvato(RADICE / "archivio/approvati", finale, {
            "atto_id": numero, "autore": a.avvocato,
            "tipo": fascicolo.get("tipo", "ricorso decreto ingiuntivo"),
            "giudice": fascicolo.get("giudice"),
            "valore": draft.totale(fascicolo) if fascicolo.get("fatture") else None,
            "data": datetime.now().date().isoformat(), "riservati": riservati})
        archive.importa_approvato(scheda, db)
        conteggio = learning.conta(modifiche)
        q = learning.quanti
        print(f"approvata da {a.avvocato}: "
              f"{q(conteggio['completamento'], 'completamento', 'completamenti')}, "
              f"{q(conteggio['dati'], 'modifica di dati', 'modifiche di dati')}, "
              f"{q(conteggio['stile'], 'correzione di stile', 'correzioni di stile')}, "
              f"{q(conteggio['riscrittura'], 'riscrittura', 'riscritture')}")
        for m in modifiche:
            if m["tipo"] == "stile":
                print(f"  stile: «{m['prima']}» → «{m['dopo']}»")
        for residuo in residui:
            print(f"  ATTENZIONE, nell'atto resta: {residuo}")
        print(f"l'atto firmato è nell'archivio come {numero}")
        return 0
    if a.comando == "fascicolo":
        try:
            dati = fatture.fascicolo([fatture.leggi(f) for f in a.fatture], a.numero, a.avvocato,
                                     date.today())
        except ValueError as errore:
            lettore.error(str(errore))
        uscita = a.uscita or RADICE / "fascicoli" / f"{a.numero}.json"
        uscita.parent.mkdir(parents=True, exist_ok=True)
        uscita.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", "utf-8")
        q = learning.quanti
        print(f"fascicolo in {uscita}: {q(len(dati['fatture']), 'fattura', 'fatture')}, "
              f"credito di euro {draft.euro(draft.totale(dati))}")
        for avvertenza in dati["avvertenze"]:
            print(f"  · {avvertenza}")
        print("  Rileggilo e completa i dati «[DA COMPLETARE]» prima di preparare la bozza.")
        return 0
    if a.comando == "word":
        markdown = a.bozza.read_text("utf-8")
        autore = next((av["id"] for av in config["avvocati"] if f"Avv. {av['nome']}" in markdown), "")
        uscita = word.scrivi(markdown, a.bozza.with_suffix(".docx"), config.get("impaginazione"),
                             carta_intestata(autore))
        print(f"bozza in Word: {uscita}")
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
        # Due bozze nello stesso secondo non si sovrascrivono: la prima resta il
        # riferimento per il confronto, se l'avvocato la approva.
        base = f"{fascicolo['id']}-{datetime.now():%Y%m%d-%H%M%S}"
        nome, n = f"{base}.md", 2
        while (a.uscita / nome).exists():
            nome, n = f"{base}-{n}.md", n + 1
        markdown = draft.in_markdown(risultato, fascicolo)
        (a.uscita / nome).write_text(markdown, "utf-8")
        in_word = word.scrivi(markdown, (a.uscita / nome).with_suffix(".docx"),
                              config.get("impaginazione"), carta_intestata(fascicolo["stile"]))
        print(f"bozza in {a.uscita / nome} e, per Word, in {in_word}")
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
