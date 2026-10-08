"""Le verifiche: che cosa può non tornare (lezione 20).

Per ogni tipo di atto, config/verifiche.json elenca le domande che un
avvocato si fa: dove guardare, quale norma leggere. Minuta le riempie con
ciò che sa senza indovinare: le righe della scheda confermata, con la loro
pagina; i controlli che fa da sola, come rifare le somme di una tabella o
riportare la scadenza confermata. Non risponde mai al posto dell'avvocato:
lo stato di ogni domanda, aperta, verificata o non pertinente, lo decide
lui.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from .scheda import in_euro

DOMANDE = Path(__file__).resolve().parents[1] / "config" / "verifiche.json"
STATI = ("aperta", "verificata", "non pertinente")
# Un importo in fondo alla riga, con i centesimi: «1.023,60», e anche
# come lo legge la lettura ottica, «3,412, 00».
IMPORTO = re.compile(r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})$")


class TipoSconosciuto(LookupError):
    """Nessun elenco di domande per quel tipo di atto."""


def carica_domande(percorso: Path = DOMANDE) -> dict:
    return json.loads(percorso.read_text("utf-8"))


def tipo_di(domande: dict, nome: str) -> str:
    """Il tipo di atto; basta l'inizio del nome, se è di un tipo solo."""
    tipi = domande["tipi"]
    simili = [t for t in tipi if t == nome or t.startswith(nome.casefold())]
    if len(simili) != 1:
        elenco = "; ".join(tipi)
        raise TipoSconosciuto(f"Tipi di atto con le domande: {elenco}.")
    return simili[0]


def importo_a_fine_riga(riga: str) -> Decimal | None:
    """L'importo con cui finisce la riga; l'ultimo separatore è quello dei
    centesimi, gli altri delle migliaia, punti o virgole che siano."""
    pulita = re.sub(r"([.,])\s+(\d)", r"\1\2", riga.strip())
    trovato = IMPORTO.search(pulita)
    if not trovato:
        return None
    cifre = re.sub(r"[.,]", "", trovato.group(1))
    return Decimal(f"{cifre[:-2]}.{cifre[-2:]}")


# [libro:somme]
def controlla_somme(pagina: str) -> list[tuple[bool, str]]:
    """Rifà le somme della pagina: le righe con un importo, una dopo
    l'altra, devono fare la riga del totale che le chiude. Per ogni totale,
    se torna e che cosa dice."""
    esiti, voci = [], []
    for riga in pagina.splitlines():
        cifra = importo_a_fine_riga(riga)
        if cifra is None:
            voci = []  # una riga senza importo chiude l'elenco
        elif riga.strip().casefold().startswith("totale") and voci:
            somma = sum(voci)
            if somma == cifra:
                esito = (
                    f"le {len(voci)} voci fanno il totale, {in_euro(cifra)}"
                )
            else:
                esito = (
                    f"le voci fanno {in_euro(somma)}, il totale dice "
                    f"{in_euro(cifra)}: {in_euro(abs(cifra - somma))} di "
                    "differenza"
                )
            esiti.append((somma == cifra, esito))
            voci = []
        else:
            voci.append(cifra)
    return esiti


# [/libro:somme]


def prepara(
    tipo: str,
    domande: dict,
    pagine: list[str],
    righe: list | None,
    scadenze: list[str],
) -> list[dict]:
    """Le domande del tipo di atto, riempite: i fatti dalla scheda
    confermata (righe, None se non c'è), i controlli di Minuta. Lo stato
    di partenza è sempre «aperta»."""
    riempite = []
    for d in domande["tipi"][tipo]:
        fatti, controlli = [], []
        if d.get("voci"):
            if righe is None:
                fatti.append("la scheda non è confermata: nessun fatto")
            else:
                fatti += [
                    f"{r.testo} (pagina {r.pagina})"
                    for r in righe
                    if r.voce in d["voci"] and not r.tolta_da and not r.manca
                ] or [
                    "nella scheda confermata nessuna riga per questa domanda"
                ]
        if d.get("controllo") == "somme":
            for n, pagina in enumerate(pagine, start=1):
                controlli += [
                    f"{'' if torna else '! '}pagina {n}: {esito}"
                    for torna, esito in controlla_somme(pagina)
                ]
            controlli = controlli or ["nessun totale da rifare"]
        if d.get("controllo") == "scadenze":
            controlli = scadenze or ["nessuna scadenza calcolata"]
        riempite.append(
            {
                "domanda": d["domanda"],
                "dove": d["dove"],
                "norma": d.get("norma"),
                "letta_il": d.get("letta_il"),
                "fatti": fatti,
                "controlli": controlli,
                "stato": "aperta",
                "deciso_da": None,
            }
        )
    return riempite
