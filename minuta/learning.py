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

# Dove finisce l'atto e cominciano le note di Minuta (draft.in_markdown). Si cerca
# l'ultima occorrenza: un «---» scritto dal modello dentro l'atto non la inganna.
NOTE = "\n---\n\n## Note per l'avvocato"


def dividi_note(markdown: str) -> tuple[str, str]:
    """La bozza divisa in due: l'atto e le note per l'avvocato."""
    testa, separatore, coda = markdown.rpartition(NOTE)
    return (testa, separatore.lstrip("\n-") + coda) if separatore else (markdown, "")


def testo_della_bozza(markdown: str) -> str:
    """Il testo della bozza, senza intestazione, provenienze e note."""
    testo = dividi_note(markdown)[0]
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


def _breve(parole: list[str]) -> bool:
    return len(parole) == 1 or (len(parole) <= 3 and all(re.fullmatch(r"[^\w\s]", p) for p in parole))


def _operazioni(a: list[str], b: list[str]) -> list[list]:
    """Le operazioni del confronto, unendo due modifiche separate da una parola
    sola o da sola punteggiatura: un punto in comune non spezza una correzione
    in due («Per le predette prestazioni» → «A fronte delle prestazioni indicate»
    è una correzione, non due)."""
    unite: list[list] = []
    for operazione in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        unite.append(list(operazione))
        while (len(unite) >= 3 and unite[-1][0] != "equal" and unite[-2][0] == "equal"
               and unite[-3][0] != "equal" and _breve(a[unite[-2][1]:unite[-2][2]])):
            ultima, _, prima = unite.pop(), unite.pop(), unite.pop()
            unite.append(["replace", prima[1], ultima[2], prima[3], ultima[4]])
    return unite


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
    for operazione, i1, i2, j1, j2 in _operazioni(a, b):
        if operazione == "equal":
            continue
        prima, dopo = a[i1:i2], b[j1:j2]
        altre = [p for p in prima if not p.startswith("[DA COMPLETARE")]
        # Un dato completato è un completamento; ma se insieme al dato sparisce
        # mezza frase, l'avvocato deve vederlo: è una riscrittura.
        if len(altre) < len(prima) and len(altre) <= PAROLE_PER_REGOLA:
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


def conta(modifiche: list[dict]) -> dict[str, int]:
    """Quante modifiche di ogni tipo. Per i completamenti conta i dati: due
    [DA COMPLETARE] vicini, completati insieme, sono due dati."""
    conteggio = dict.fromkeys(TIPI, 0)
    for m in modifiche:
        conteggio[m["tipo"]] += (max(1, m["prima"].count("[DA COMPLETARE"))
                                 if m["tipo"] == "completamento" else 1)
    return conteggio


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
                          modifiche: list[dict], firmato: str,
                          residui: list[str] | None = None) -> dict:
    voce = {
        "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evento": "approvazione", "fascicolo": fascicolo, "bozza": bozza,
        "approvata_da": avvocato,
        "firmato_sha256": hashlib.sha256(firmato.encode()).hexdigest(),
        "modifiche": conta(modifiche),
        # Ciò che di Minuta restava nell'atto, se l'avvocato l'ha registrato comunque.
        "residui": residui or [],
    }
    cartella.mkdir(parents=True, exist_ok=True)
    with open(cartella / "uso-ai.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")
    return voce
