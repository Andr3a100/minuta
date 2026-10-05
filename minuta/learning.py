"""Come Minuta impara dall'avvocato, senza addestrare nessun modello.

Tre strumenti, tutti in file che l'avvocato può leggere e correggere:
- la curatela: quali atti sono buoni esempi e quali no;
- le correzioni: che cosa l'avvocato cambia nelle bozze, prima di firmarle;
- l'archivio: ogni atto firmato entra fra gli esempi delle bozze successive.

Le correzioni si confrontano sul testo pseudonimizzato: le regole che ne
nascono parlano di stile, non di clienti.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .archive import MESI
from .pseudonym import Pseudonimizzatore

# Un importo, una data o un numero di fattura sono una parola sola: «9.960,50», «455/2025».
NUMERO = r"\d+(?:[.,/:\-]\d+)*"
PAROLA = re.compile(rf"\[[^\]\n]+\]|{NUMERO}|[\wà-ùÀ-Ù'’]+|[^\w\s]")
DATO = re.compile(rf"{NUMERO}|\[[A-Z_]+\]|[^\w\s]|{'|'.join(MESI)}", re.I)
PAGINA = re.compile(r"(?:pag(?:ina|\.)?\s*)?\d+(?:\s*(?:di|/)\s*\d+)?", re.I)
# Una regola nasce da correzioni uguali in atti diversi: in un atto solo può
# essere un caso; e una correzione lunga è una riscrittura, non una regola.
QUANTE_PER_REGOLA = 2
PAROLE_PER_REGOLA = 12
TIPI = ("completamento", "dati", "stile", "riscrittura")


def quanti(n: int, uno: str, molti: str) -> str:
    """«1 atto», «2 atti»: l'avvocato legge queste righe, devono essere italiano."""
    return f"{n} {uno if n == 1 else molti}"


# --- La curatela degli esempi ------------------------------------------------

def carica_curatela(percorso: Path) -> dict:
    if percorso.exists():
        return json.loads(percorso.read_text("utf-8"))
    return {"esempi": {}}


def segna_esempio(percorso: Path, atto_id: str, buono: bool, motivo: str = "") -> dict:
    curatela = carica_curatela(percorso)
    curatela["esempi"][atto_id] = {"esempio": buono, "motivo": motivo,
                                   "deciso_il": date.today().isoformat()}
    percorso.write_text(json.dumps(curatela, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return curatela


def esclusi(curatela: dict) -> set[str]:
    return {i for i, v in curatela.get("esempi", {}).items() if v.get("esempio") is False}


def preferiti(curatela: dict) -> set[str]:
    return {i for i, v in curatela.get("esempi", {}).items() if v.get("esempio") is True}


# --- Dalla bozza all'atto firmato -------------------------------------------

def testo_della_bozza(markdown: str) -> str:
    """Il testo della bozza, senza intestazione, provenienze e note."""
    testo = markdown.split("\n---\n", 1)[0]
    testo = re.sub(r"^>.*$", "", testo, flags=re.M)
    testo = re.sub(r"<sub>provenienza:[^<]*</sub>", "", testo)
    testo = re.sub(r"[*#]", "", testo)
    return re.sub(r"\n{3,}", "\n\n", testo).strip()


def testo_firmato(paragrafi: list[str]) -> str:
    """L'atto firmato, letto dal PDF, senza i numeri di pagina: non sono correzioni."""
    return "\n\n".join(p for p in paragrafi if not PAGINA.fullmatch(p.strip()))


def _scrivi(parole: list[str]) -> str:
    testo = " ".join(parole)
    testo = re.sub(r"\s+([.,;:)\]»])", r"\1", testo)
    return re.sub(r"([(«\[])\s+", r"\1", testo)


def _generalizza(parole: list[str]) -> list[str]:
    """Importi, date e numeri diventano [NUMERO]: nelle regole resta lo stile, non i fatti."""
    return ["[NUMERO]" if re.fullmatch(NUMERO, p) else p for p in parole]


def confronta(bozza: str, finale: str, noti: dict[str, str] | None = None) -> list[dict]:
    """Le modifiche dell'avvocato, ciascuna con il suo tipo.

    - completamento: un [DA COMPLETARE] riempito;
    - dati: cambiano solo numeri, date, segnaposto o punteggiatura (i fatti, non
      lo stile: una virgola spostata due volte non deve diventare una regola);
    - stile: cambiano le parole. È ciò da cui Minuta impara;
    - riscrittura: un passaggio rifatto per intero. Si conta, ma non diventa regola.
    """
    a = PAROLA.findall(Pseudonimizzatore(generico=True, noti=dict(noti or {})).nascondi(bozza))
    b = PAROLA.findall(Pseudonimizzatore(generico=True, noti=dict(noti or {})).nascondi(finale))
    modifiche = []
    for operazione, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if operazione == "equal":
            continue
        prima, dopo = a[i1:i2], b[j1:j2]
        if any(p.startswith("[DA COMPLETARE") for p in prima):
            tipo = "completamento"
        elif all(DATO.fullmatch(p) for p in prima + dopo):
            tipo = "dati"
        elif max(len(prima), len(dopo)) > PAROLE_PER_REGOLA:
            tipo = "riscrittura"
        else:
            tipo = "stile"
            prima, dopo = _generalizza(prima), _generalizza(dopo)
        modifiche.append({"tipo": tipo, "prima": _scrivi(prima), "dopo": _scrivi(dopo),
                          "contesto": _scrivi(_generalizza(a[max(0, i1 - 4):i1]))})
    return modifiche


def aggiorna_correzioni(percorso: Path, autore: str, fascicolo: str,
                        modifiche: list[dict]) -> dict:
    """Aggiunge le correzioni di stile al registro delle correzioni."""
    dati = json.loads(percorso.read_text("utf-8")) if percorso.exists() else {}
    voci = dati.setdefault(autore, {})
    for m in modifiche:
        if m["tipo"] != "stile":
            continue
        chiave = f"{m['prima']} → {m['dopo']}"
        voce = voci.setdefault(chiave, {"prima": m["prima"], "dopo": m["dopo"], "volte": 0,
                                        "fascicoli": [], "contesti": []})
        voce["volte"] += 1
        if fascicolo not in voce["fascicoli"]:
            voce["fascicoli"].append(fascicolo)
        if m["contesto"] and m["contesto"] not in voce["contesti"]:
            voce["contesti"].append(m["contesto"])
    percorso.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return dati


def voci_ordinate(percorso: Path, autore: str) -> list[dict]:
    """Le correzioni di un avvocato, dalla più confermata: è l'ordine dei numeri
    che il comando «correzioni» mostra e che «--respingi» usa."""
    if not percorso.exists():
        return []
    voci = json.loads(percorso.read_text("utf-8")).get(autore, {})
    return sorted(voci.values(), key=lambda v: (-len(v["fascicoli"]), -v["volte"],
                                                v["prima"], v["dopo"]))


def e_regola(voce: dict, minimo: int = QUANTE_PER_REGOLA) -> bool:
    return len(voce["fascicoli"]) >= minimo and not voce.get("respinta")


def voci_regola(percorso: Path, autore: str, minimo: int = QUANTE_PER_REGOLA) -> list[dict]:
    """Le correzioni diventate regole: fatte in almeno «minimo» atti, mai respinte."""
    return [v for v in voci_ordinate(percorso, autore) if e_regola(v, minimo)]


def come_regola(voce: dict) -> str:
    atti = quanti(len(voce["fascicoli"]), "atto", "atti")
    if voce["prima"] and voce["dopo"]:
        return f"Scrivi «{voce['dopo']}», non «{voce['prima']}» (corretto in {atti})."
    if voce["dopo"]:
        dove = f"dopo «{voce['contesti'][0]}»" if voce["contesti"] else "all'inizio dell'atto"
        return f"Aggiungi «{voce['dopo']}» {dove} (aggiunto in {atti})."
    return f"Non scrivere «{voce['prima']}» (tolto in {atti})."


def regole_apprese(percorso: Path, autore: str, minimo: int = QUANTE_PER_REGOLA) -> list[str]:
    return [come_regola(v) for v in voci_regola(percorso, autore, minimo)]


def _schema(frase: str) -> str:
    parole = PAROLA.findall(frase)
    schema = r"\s*".join(NUMERO if p == "[NUMERO]" else re.escape(p) for p in parole)
    if re.match(r"\w", parole[0]):
        schema = r"(?<![\w\[])" + schema
    if re.search(r"\w$", parole[-1]):
        schema += r"(?![\w\]])"
    return schema


def non_rispettate(testo: str, voci: list[dict], noti: dict[str, str] | None = None) -> list[str]:
    """Le regole apprese che la bozza non segue. Il modello le ha lette, ma
    leggere non è seguire: come le regole dello studio, si controllano dopo."""
    generico = Pseudonimizzatore(generico=True, noti=dict(noti or {})).nascondi(testo)
    avvisi = []
    for voce in voci:
        if voce["prima"] and re.search(_schema(voce["prima"]), generico, re.I):
            correzione = (f"corretto in «{voce['dopo']}»" if voce["dopo"] else "tolto")
            avvisi.append(f"REGOLA APPRESA NON SEGUITA: la bozza scrive ancora «{voce['prima']}», "
                          f"che l'avvocato ha {correzione} in "
                          f"{quanti(len(voce['fascicoli']), 'atto', 'atti')}.")
    return avvisi


def respingi(percorso: Path, autore: str, numero: int) -> dict:
    """L'avvocato dice che una correzione non va generalizzata: resta nel registro,
    ma non diventa mai regola."""
    voci = voci_ordinate(percorso, autore)
    if not 1 <= numero <= len(voci):
        raise ValueError(f"non c'è la correzione numero {numero} per {autore}")
    voce = voci[numero - 1]
    dati = json.loads(percorso.read_text("utf-8"))
    scelta = dati[autore][f"{voce['prima']} → {voce['dopo']}"]
    scelta["respinta"] = date.today().isoformat()
    percorso.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return scelta


def registra_approvazione(cartella: Path, fascicolo: str, bozza: str, avvocato: str,
                          modifiche: list[dict], firmato: str) -> dict:
    voce = {
        "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evento": "approvazione", "fascicolo": fascicolo, "bozza": bozza,
        "approvata_da": avvocato,
        "firmato_sha256": hashlib.sha256(firmato.encode()).hexdigest(),
        "modifiche": {t: sum(1 for m in modifiche if m["tipo"] == t) for t in TIPI},
    }
    cartella.mkdir(parents=True, exist_ok=True)
    with open(cartella / "uso-ai.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")
    return voce
