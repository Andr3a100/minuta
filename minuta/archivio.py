"""L'archivio dello studio: gli atti già firmati, da cui si impara come si
scrive (lezione 22).

Ogni atto entra con le sue pagine, con i dati che Minuta legge dall'atto
stesso (tipo, autore, data, giudice, valore) e con le persone da nascondere,
che vengono dall'indice dello studio. Si cerca per parole, come nelle
domande sul fascicolo (lezione 21), e per tipo, autore e periodo; la ricerca
resta nello studio. Quando le pagine di un atto partono verso un modello, i
nomi dei suoi clienti diventano segnaposto, e segnaposto restano anche nella
risposta: un precedente insegna la forma, non i fatti di un altro cliente.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import archive
from .domande import Passo, parole, scegli_passi

SOCIETA = re.compile(
    r"\b(s\.?r\.?l|s\.?p\.?a|s\.?n\.?c|s\.?a\.?s|studio)\b", re.IGNORECASE
)


class IndiceIncompleto(LookupError):
    """Un atto che l'indice dello studio non conosce."""


@dataclass
class AttoLetto:
    """Ciò che serve per cercare in un atto dell'archivio."""

    numero: int
    tipo: str | None
    autore: str | None  # il nome utente dell'avvocato che l'ha firmato
    data: date | None
    pagine: list[str]


@dataclass
class Trovato:
    atto: AttoLetto
    pagine: dict[int, list[str]]  # numero della pagina: parole in comune

    @property
    def punti(self) -> int:
        """Le parole in comune della pagina migliore."""
        return max(len(comuni) for comuni in self.pagine.values())


def etichetta(numero: int) -> str:
    """Il nome con cui un atto parte verso il modello: mai il nome del file,
    che spesso contiene quello del cliente."""
    return f"archivio-{numero:02d}"


def leggi_indice(percorso: Path) -> dict[str, list[str]]:
    """Le persone da nascondere di ogni atto, dall'indice dello studio: un
    file CSV con le colonne file, ricorrente e controparte, e se serve la
    colonna altre, con altri nomi separati da virgole."""
    with percorso.open(encoding="utf-8", newline="") as f:
        indice = {}
        for riga in csv.DictReader(f, delimiter=";"):
            nomi = [riga["ricorrente"], riga["controparte"]]
            nomi += (riga.get("altre") or "").split(",")
            indice[riga["file"].strip()] = [
                n.strip() for n in nomi if n.strip()
            ]
        return indice


def tipo_del_nome(nome: str) -> str:
    """Società e studi sono soggetti, gli altri persone."""
    return "SOGGETTO" if SOCIETA.search(nome) else "PERSONA"


def dati_dell_atto(percorso: Path, avvocati: list[dict]) -> dict:
    """Tipo, autore, data, giudice e valore, letti dall'atto stesso."""
    atto = archive.leggi_atto(percorso, avvocati)
    return {
        "tipo": atto.tipo,
        "autore": atto.autore,
        "data": date.fromisoformat(atto.data) if atto.data else None,
        "giudice": atto.giudice,
        "valore": atto.valore,
    }


# [libro:filtra]
def filtra(
    atti: list[AttoLetto],
    tipo: str | None = None,
    autore: str | None = None,
    dal: date | None = None,
    al: date | None = None,
) -> list[AttoLetto]:
    """Gli atti di un tipo (basta l'inizio del nome), di un autore, di un
    periodo. Un atto senza data non sta in nessun periodo."""
    scelti = []
    for atto in atti:
        if tipo and not (atto.tipo or "").startswith(tipo.casefold()):
            continue
        if autore and atto.autore != autore:
            continue
        if (dal or al) and atto.data is None:
            continue
        if dal and atto.data < dal:
            continue
        if al and atto.data > al:
            continue
        scelti.append(atto)
    return scelti


# [/libro:filtra]


# [libro:cerca]
def cerca(testo: str, atti: list[AttoLetto]) -> list[Trovato]:
    """Gli atti con le parole cercate, e per ogni pagina quali. Prima gli
    atti con più parole sulla stessa pagina: parole vicine dicono di più
    di parole sparse per l'atto."""
    cercate = parole(testo)
    trovati = []
    for atto in atti:
        pagine = {}
        for numero, pagina in enumerate(atto.pagine, start=1):
            comuni = sorted(cercate & parole(pagina))
            if comuni:
                pagine[numero] = comuni
        if pagine:
            trovati.append(Trovato(atto, pagine))
    return sorted(trovati, key=lambda t: (-t.punti, t.atto.numero))


# [/libro:cerca]


def passi_dell_archivio(domanda: str, atti: list[AttoLetto]) -> list[Passo]:
    """Le pagine dell'archivio da mandare per una domanda: le stesse regole
    delle domande sul fascicolo, con l'etichetta al posto del nome."""
    return scegli_passi(domanda, {etichetta(a.numero): a.pagine for a in atti})
