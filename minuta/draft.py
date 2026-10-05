"""La bozza: dal fascicolo e dai precedenti dello studio, con la sua provenienza.

Il percorso è sempre lo stesso, e ogni passo lascia una traccia:
1. cerca nell'archivio i precedenti più vicini, nello stile scelto;
2. pseudonimizza il fascicolo e gli esempi, ciascuno con il suo prefisso;
3. controlla che niente di riconoscibile stia per partire;
4. chiede la bozza al modello e registra la chiamata;
5. scarta i segnaposto di altri fascicoli, ricompone i nomi veri;
6. verifica ogni citazione sul massimario;
7. consegna una BOZZA, con la provenienza di ogni paragrafo.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import archive, citations, learning, search
from .leaks import fughe
from .model import Modello
from .pseudonym import Pseudonimizzatore, segnaposto_estranei

SISTEMA = """Sei l'assistente di uno studio legale italiano. Prepari BOZZE che un \
avvocato rivedrà, correggerà e firmerà: non scrivi mai un atto definitivo.
Regole:
1. Usa solo i fatti del FASCICOLO. Se manca un dato, scrivi [DA COMPLETARE: che cosa manca].
2. Cita solo le norme dell'elenco CITAZIONI AMMESSE. Se ne serve un'altra, scrivila preceduta \
da [DA VERIFICARE]. Non citare mai sentenze che non ti sono state date.
3. Mantieni i segnaposto fra parentesi quadre esattamente come sono. Non usare mai i \
segnaposto degli esempi (quelli che cominciano con E1_ o E2_): appartengono ad altri clienti.
4. Segui lo STILE dello studio: intestazione, titolo, ordine delle sezioni, formule.
5. Alla fine di ogni paragrafo scrivi la sua provenienza fra parentesi graffe: \
{fonte: fascicolo}, {fonte: profilo}, {fonte: E1}, {fonte: E2}, oppure {fonte: modello} se è \
un testo tuo."""

TITOLI_STILE = {
    "sarti": {"fatti": "PREMESSO CHE", "diritto": "CONSIDERATO CHE",
              "conclusioni": "TUTTO CIÒ PREMESSO E CONSIDERATO, la ricorrente CHIEDE"},
    "dini": {"fatti": "1. I fatti", "diritto": "2. Il credito e la prova scritta",
             "conclusioni": "3. Conclusioni"},
}


# Elementi che cambiano la natura di un ricorso. Se la bozza ne parla e il
# fascicolo no, il passaggio viene quasi sempre da un precedente di un altro
# cliente: le norme citate esistono, ma non si applicano a questo caso.
ELEMENTI = {
    "assegno o cambiale": r"\bassegn[oi]\b|\bcambial[ei]\b|\bprotest",
    "provvisoria esecuzione": r"provvisori[ae] esecuzione|esecuzione provvisoria|"
                              r"provvisoriamente esecutivo|\bart\. 642\b",
    "riconoscimento di debito": r"riconosciment[oi] del debito|piano di rientro",
    "locazione": r"\blocazion|\bconduttore\b|\blocatore\b",
    "consumatore": r"\bconsumator|scopi estranei all'attività",
    "subappalto": r"\bsubappalt",
}


def pertinenza(paragrafi: list[dict], fascicolo: dict) -> list[str]:
    """Gli elementi presenti nella bozza ma assenti dal fascicolo."""
    fatti = json.dumps(fascicolo, ensure_ascii=False).lower()
    avvisi = []
    for elemento, regola in ELEMENTI.items():
        if re.search(regola, fatti, re.I):
            continue
        dove = [f"{n} ({p['fonte']})" for n, p in enumerate(paragrafi, start=1)
                if re.search(regola, p["testo"], re.I)]
        if dove:
            avvisi.append(f"PERTINENZA: la bozza parla di {elemento} (paragrafi {', '.join(dove)}), "
                          "ma il fascicolo no. Verificare se si applica a questo caso.")
    return avvisi


def regole_dello_studio(fascicolo: dict) -> list[str]:
    """Le regole per questo tipo di atto, con i numeri del fascicolo.

    Sono le stesse che completezza() controlla dopo: dirle prima al modello
    evita l'errore, controllarle dopo lo intercetta se succede comunque.
    """
    regole = []
    if fascicolo["tipo"].startswith("ricorso decreto ingiuntivo"):
        regole += [
            "Indica il termine di quaranta giorni per pagare o proporre opposizione (art. 641 c.p.c.).",
            "Dichiara il valore della procedura ai sensi dell'art. 14 del D.P.R. 115/2002.",
            "Elenca i documenti prodotti.",
        ]
        if fascicolo.get("interessi") == "commerciali":
            fatture = len(fascicolo.get("fatture", []))
            regole.append(
                "Transazione commerciale: chiedi gli interessi moratori dell'art. 5 del D.Lgs. 231/2002 "
                f"e, per ciascuna fattura, 40 euro per i costi di recupero: qui {fatture} fatture, "
                f"euro {euro(40 * fatture)} (art. 6 del D.Lgs. 231/2002, come interpretato dalla "
                "Corte di giustizia UE, C-585/20).")
        if fascicolo.get("provvisoria_esecuzione"):
            regole.append("Chiedi la provvisoria esecuzione ai sensi dell'art. 642 c.p.c., "
                          "indicandone il presupposto.")
    return regole


def completezza(testo: str, fascicolo: dict) -> list[str]:
    """Ciò che un ricorso di questo tipo deve contenere e la bozza non ha."""
    avvisi = []
    if not fascicolo["tipo"].startswith("ricorso decreto ingiuntivo"):
        return avvisi
    richiesti = [
        ("la dichiarazione di valore (art. 14 D.P.R. 115/2002)", r"valore della (?:presente procedura|causa)"),
        ("il termine di quaranta giorni per pagare o fare opposizione", r"quaranta giorni"),
        ("l'elenco dei documenti prodotti", r"si producono|documenti"),
    ]
    for cosa, regola in richiesti:
        if not re.search(regola, testo, re.I):
            avvisi.append(f"COMPLETEZZA: manca {cosa}.")
    if fascicolo.get("interessi") == "commerciali":
        fatture = len(fascicolo.get("fatture", []))
        if not re.search(r"art\. 6\b[^.;]{0,40}231|costi di recupero", testo, re.I):
            avvisi.append(
                f"COMPLETEZZA: transazione commerciale, manca la richiesta dei 40 euro per ciascuna "
                f"fattura ({fatture} fatture, euro {euro(40 * fatture)}): art. 6 del D.Lgs. 231/2002, "
                "come interpretato dalla Corte di giustizia UE, C-585/20.")
    if fascicolo.get("provvisoria_esecuzione") and not re.search(r"\b642\b", testo):
        avvisi.append("COMPLETEZZA: il fascicolo chiede la provvisoria esecuzione, la bozza no.")
    return avvisi


@dataclass
class Bozza:
    testo: str
    modello: str
    paragrafi: list[dict] = field(default_factory=list)  # testo, fonte
    citazioni: list[dict] = field(default_factory=list)
    avvisi: list[str] = field(default_factory=list)
    esempi: list[str] = field(default_factory=list)
    inviato: str = ""


def euro(valore: float) -> str:
    return f"{valore:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_it(iso: str) -> str:
    anno, mese, giorno = iso.split("-")
    return f"{giorno}.{mese}.{anno}"


def sensibili_del_fascicolo(fascicolo: dict) -> dict[str, str]:
    """I dati del fascicolo da non far uscire, con il loro tipo."""
    noti = {}
    for parte in ("ricorrente", "intimata"):
        dati = fascicolo[parte]
        noti[dati["nome"]] = "SOGGETTO"
        noti[dati["piva"]] = "PIVA"
        noti[dati["sede"]] = "INDIRIZZO"
        if dati.get("rappresentante"):
            noti[dati["rappresentante"]] = "PERSONA"
    return noti


def dati_del_fascicolo(fascicolo: dict, avvocato: str) -> str:
    totale = sum(f["importo"] for f in fascicolo["fatture"])
    fatture = ", ".join(f"n. {f['numero']} del {data_it(f['data'])} (euro {euro(f['importo'])})"
                        for f in fascicolo["fatture"])
    r, i = fascicolo["ricorrente"], fascicolo["intimata"]
    righe = {
        "TIPO DI ATTO": fascicolo["tipo"], "GIUDICE": fascicolo["giudice"],
        "RICORRENTE": r["nome"], "PIVA RICORRENTE": r["piva"], "SEDE RICORRENTE": r["sede"],
        "RAPPRESENTANTE": r.get("rappresentante", "[DA COMPLETARE]"),
        "INTIMATA": i["nome"], "PIVA INTIMATA": i["piva"], "SEDE INTIMATA": i["sede"],
        "AVVOCATO": avvocato, "RAPPORTO": fascicolo["rapporto"], "FATTURE": fatture,
        "TOTALE": euro(totale), "DIFFIDA": data_it(fascicolo["diffida"]),
        "INTERESSI": fascicolo.get("interessi", ""), "DOCUMENTI": "; ".join(fascicolo["documenti"]),
    }
    return "\n".join(f"{k}: {v}" for k, v in righe.items())


def costo(modello: str, token_in: int | None, token_out: int | None, prezzi: dict) -> float | None:
    """Il costo in dollari, dai prezzi ufficiali registrati in config/prezzi.json."""
    voce = next((v for k, v in prezzi.items() if not k.startswith("_") and modello.startswith(k)), None)
    if voce is None or token_in is None or token_out is None:
        return None
    return round((token_in * voce["ingresso"] + token_out * voce["uscita"]) / 1_000_000, 4)


def registra(cartella: Path, voce: dict) -> None:
    cartella.mkdir(parents=True, exist_ok=True)
    with open(cartella / "uso-ai.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")


def scegli_esempi(db: sqlite3.Connection, stile: str, domanda: str, curatela: dict,
                  quanti: int = 2) -> list[search.Risultato]:
    """Gli atti che fanno da esempio: dello stesso avvocato e dello stesso tipo.

    Prima i più vicini per argomento. Per imitare uno stile non servono atti
    sullo stesso argomento, quindi se la ricerca non basta si aggiungono i
    modelli indicati dall'avvocato e poi i più recenti; mai gli atti esclusi.
    """
    esclusi = learning.esclusi(curatela)
    trovati = search.cerca(db, domanda, tipo="ricorso", autore=stile, quanti=quanti,
                           escludi=esclusi)
    candidati = [r for r in db.execute(
        "select * from atti where autore = ? and tipo like 'ricorso%' order by data desc",
        (stile,)) if r["id"] not in esclusi]
    buoni = learning.preferiti(curatela)
    candidati.sort(key=lambda r: r["id"] not in buoni)
    for riga in candidati:
        if len(trovati) >= quanti:
            break
        if riga["id"] not in {r.atto_id for r in trovati}:
            trovati.append(search.Risultato(riga["id"], riga["file"], 0.0, riga["autore"],
                                            riga["tipo"], riga["data"], "esempio di stile"))
    # Gli atti approvati sono nati da bozze di Minuta. Se fossero tutti gli
    # esempi, bozza dopo bozza lo stile scivolerebbe verso quello del modello:
    # almeno un esempio resta un atto scritto dall'avvocato senza Minuta.
    approvati = archive.approvati(db)
    if trovati and all(r.atto_id in approvati for r in trovati):
        originali = search.cerca(db, domanda, tipo="ricorso", autore=stile, quanti=1,
                                 escludi=esclusi | approvati) or [
            search.Risultato(r["id"], r["file"], 0.0, r["autore"], r["tipo"], r["data"],
                             "esempio di stile")
            for r in candidati if r["id"] not in approvati][:1]
        if originali:
            trovati[-1] = originali[0]
    return trovati


def prepara(db: sqlite3.Connection, fascicolo: dict, config: dict, profilo: dict,
            massimario: citations.Massimario, modello: Modello, registro: Path,
            prezzi: dict | None = None, curatela: dict | None = None,
            apprese: list[dict] | None = None) -> Bozza:
    stile = fascicolo["stile"]
    avvocato = next(a["nome"] for a in config["avvocati"] if a["id"] == stile)

    # 1. I precedenti più vicini, nello stile dell'avvocato che firmerà.
    trovati = scegli_esempi(db, stile, fascicolo["rapporto"], curatela or {})

    # 2. Pseudonimizzazione: il fascicolo senza prefisso, ogni esempio con il suo.
    noti = {config["studio"]: "STUDIO", avvocato: "PERSONA", **sensibili_del_fascicolo(fascicolo)}
    fascicolo_ps = Pseudonimizzatore(noti=noti)
    dati = fascicolo_ps.nascondi(dati_del_fascicolo(fascicolo, avvocato))
    sensibili = set(noti) | set(fascicolo_ps.tabella.values())
    blocchi_esempi = []
    for n, risultato in enumerate(trovati, start=1):
        testo = db.execute("select testo from atti where id = ?", (risultato.atto_id,)).fetchone()[0]
        # Un atto firmato porta con sé i dati del suo cliente: si nascondono e si
        # cercano nel testo in uscita, anche dove nessuna regola li riconoscerebbe.
        riservati = archive.riservati(db, risultato.atto_id)
        esempio_ps = Pseudonimizzatore(prefisso=f"E{n}_",
                                       noti={config["studio"]: "STUDIO", **riservati})
        nascosto = esempio_ps.nascondi(testo)
        sensibili |= set(esempio_ps.tabella.values()) | set(riservati)
        blocchi_esempi.append(f"ESEMPIO E{n} (atto {risultato.atto_id}, {risultato.data})\n{nascosto}")

    regole = profilo["autori"][stile]
    stile_json = json.dumps({"intestazione": regole["intestazione"], "titolo": regole["titolo"],
                             "sezioni": regole["sezioni"], **TITOLI_STILE[stile],
                             "formule": list(regole["formule_proprie"])[:8]},
                            ensure_ascii=False)
    richiesta = "\n".join([
        dati, f"STILE: {stile_json}",
        "REGOLE DELLO STUDIO: " + " ".join(regole_dello_studio(fascicolo)),
        "REGOLE APPRESE DALLE CORREZIONI DELL'AVVOCATO: "
        + (" ".join(learning.come_regola(v) for v in apprese or []) or "nessuna"),
        "CITAZIONI AMMESSE: " + "; ".join(massimario.ammesse()),
        *blocchi_esempi, "FINE ESEMPI",
        "Scrivi la bozza completa dell'atto."])

    # 3. La prova delle fughe: se qualcosa di riconoscibile sta per partire, ci si ferma.
    trovate = fughe(SISTEMA + "\n" + richiesta, sensibili)
    if trovate:
        raise RuntimeError(f"invio bloccato, dati riconoscibili nel testo: {trovate}")

    # 4. La chiamata al modello, registrata.
    risposta = modello.scrivi(SISTEMA, richiesta)
    registra(registro, {
        "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fascicolo": fascicolo["id"], "modello": risposta.modello,
        "inviato_sha256": hashlib.sha256((SISTEMA + richiesta).encode()).hexdigest(),
        "caratteri_inviati": len(SISTEMA + richiesta), "token_in": risposta.token_in,
        "token_out": risposta.token_out,
        "costo_usd": costo(risposta.modello, risposta.token_in, risposta.token_out, prezzi or {}),
        "esempi": [r.atto_id for r in trovati],
        "controllo_fughe": "superato", "approvata_da": None})

    # 5. Segnaposto di altri fascicoli: non si ricompongono mai.
    avvisi = []
    estranei = segnaposto_estranei(risposta.testo)
    if estranei:
        avvisi.append(f"CONTAMINAZIONE: la bozza usa segnaposto di altri fascicoli {estranei}; "
                      "quei passaggi vanno riscritti.")
    paragrafi = []
    for blocco in re.split(r"\n\s*\n", risposta.testo.strip()):
        fonte = re.search(r"\{fonte:\s*([^}]+)\}\s*$", blocco)
        testo = re.sub(r"\s*\{fonte:[^}]*\}\s*$", "", blocco).strip()
        paragrafi.append({"testo": fascicolo_ps.ricomponi(testo),
                          "fonte": fonte.group(1).strip() if fonte else "non dichiarata"})
    avvisi += pertinenza(paragrafi, fascicolo)
    senza_fonte = [p for p in paragrafi if p["fonte"] == "non dichiarata"]
    if senza_fonte:
        avvisi.append(f"{len(senza_fonte)} paragrafi senza provenienza dichiarata.")
    testo = "\n\n".join(p["testo"] for p in paragrafi)

    # 6. Le citazioni, una per una.
    stati = citations.controlla(testo, massimario)
    for c in stati:
        if c["stato"] != "verificata":
            avvisi.append(f"Citazione {c['stato']}: «{c['citazione']}».")
    avvisi += completezza(testo, fascicolo)
    avvisi += learning.non_rispettate(testo, apprese or [], noti)
    if "[DA COMPLETARE" in testo:
        avvisi.append("Dati da completare: " + "; ".join(re.findall(r"\[DA COMPLETARE: ([^\]]+)\]", testo)))

    return Bozza(testo, risposta.modello, paragrafi, stati, avvisi,
                 [r.atto_id for r in trovati], richiesta)


def in_markdown(bozza: Bozza, fascicolo: dict) -> str:
    """La bozza come la legge l'avvocato: testo, provenienza, note."""
    adesso = datetime.now().strftime("%d.%m.%Y %H:%M")
    righe = [f"> **BOZZA** · fascicolo {fascicolo['id']} · preparata da Minuta il {adesso} "
             f"con il modello «{bozza.modello}» · esempi dall'archivio: "
             f"{', '.join(bozza.esempi) or 'nessuno'}. Non è un atto: va riletta, corretta e "
             "firmata da un avvocato.", ""]
    for p in bozza.paragrafi:
        righe += [p["testo"], "", f"<sub>provenienza: {p['fonte']}</sub>", ""]
    righe += ["---", "", "## Note per l'avvocato", ""]
    righe += [f"- {a}" for a in bozza.avvisi] or ["- Nessun avviso."]
    righe += ["", "## Citazioni", ""]
    righe += [f"- {c['citazione']} · {c['stato']}" for c in bozza.citazioni]
    return "\n".join(righe) + "\n"
