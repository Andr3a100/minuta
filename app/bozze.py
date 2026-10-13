"""Le bozze, nell'applicazione (lezione 24).

Avvocati e praticanti chiedono una bozza per un fascicolo a cui lavorano.
L'atto si scrive nello stile dell'avvocato del fascicolo, quello che lo
firmerà, e solo se il suo profilo è confermato (lezione 23). Partono i
documenti del fascicolo e le scadenze confermate, pseudonimizzati come ogni
richiesta (lezione 17); la bozza torna con i nomi veri e con i controlli di
Minuta, si conserva con la voce del registro dell'uso dell'AI e si porta in
Word, impaginata secondo l'art. 6 del DM 110/2023.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta import word
from minuta.bozza import (
    Paragrafo,
    controlla,
    da_completare,
    da_verificare,
    in_markdown,
    istruzioni,
    leggi_bozza,
    manca_la_scadenza,
)
from minuta.domande import Passo, a_passi
from minuta.invio import SISTEMA, Preparato, prepara, ricomponi
from minuta.model import Modello
from minuta.scadenze import in_lettere

from .db import Bozza, Fascicolo, Scadenza, UsoAI, Utente, adesso
from .invio import (
    InvioBloccato,
    categorie,
    chi_chiede,
    noti_del_fascicolo,
    salva_segnaposto,
    tabella_del_fascicolo,
    testo_nascosto,
)
from .registro import RichiestaNonAmmessa, chiedi
from .risposte import documenti_del_fascicolo
from .stile import letto, ultimo_profilo
from .web import registra_evento


class BozzaRifiutata(Exception):
    """La bozza non si prepara: il messaggio dice perché."""


@dataclass
class EsitoBozza:
    bozza: Bozza
    paragrafi: list[Paragrafo]
    note: list[str]
    preparato: Preparato
    arrivata: str
    voce: UsoAI
    stile: str | None  # di chi è lo stile, per l'atto


def stile_di(db: Session, fascicolo: Fascicolo) -> tuple[Utente, str]:
    """Lo stile dell'avvocato che firmerà: solo dal profilo confermato, e
    solo le formule tenute nello stile."""
    avvocato = db.get(Utente, fascicolo.avvocato_id)
    profilo = ultimo_profilo(db, avvocato)
    if profilo is None or profilo.confermato_il is None:
        raise BozzaRifiutata(
            f"L'atto si scrive nello stile di {avvocato.nome}: serve il suo "
            "profilo, confermato (lezione 23)."
        )
    dati = letto(profilo)
    formule = [f["testo"] for f in dati["formule"] if f["stato"] == "stile"]
    righe = [
        f"Intestazione: {dati['intestazione']}",
        f"Titolo dei suoi ricorsi: {dati['titolo']}",
        f"Parole per frase, in media: {dati['parole_per_frase']}",
        "Formule:",
        *(f"- {f}" for f in formule),
    ]
    return avvocato, "\n".join(righe)


def scadenze_confermate(db: Session, fascicolo: Fascicolo):
    return list(
        db.scalars(
            select(Scadenza)
            .where(
                Scadenza.fascicolo_id == fascicolo.id,
                Scadenza.confermata_da_id.is_not(None),
            )
            .order_by(Scadenza.id)
        )
    )


def righe_delle_scadenze(scadenze) -> str:
    return "\n".join(
        f"- {s.termine}: {in_lettere(s.scadenza)} ({s.norma}), dalla "
        f"notificazione del {in_lettere(s.partenza)}"
        for s in scadenze
    )


# [libro:prepara-bozza]
def prepara_bozza(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    tipo: str,
    modello: Modello,
) -> EsitoBozza:
    if utente.ruolo == "segreteria":
        raise RichiestaNonAmmessa("La segreteria non fa richieste al modello.")
    regole = istruzioni(tipo)
    avvocato, stile = (
        stile_di(db, fascicolo) if tipo == "opposizione" else (None, "")
    )
    documenti, pagine = documenti_del_fascicolo(db, fascicolo)
    scadenze = scadenze_confermate(db, fascicolo)
    passi = [
        Passo(nome, n, testo)
        for nome, testi in pagine.items()
        for n, testo in enumerate(testi, start=1)
    ]
    testo = (
        f"{regole}\n\nCHI CHIEDE: {chi_chiede(utente, fascicolo)}\n\n"
        + (f"STILE:\n{stile}\n\n" if stile else "")
        + f"SCADENZE:\n{righe_delle_scadenze(scadenze) or 'nessuna'}\n\n"
        + a_passi(passi)
    )
    noti = noti_del_fascicolo(db, fascicolo)
    preparato = prepara(testo, noti, tabella_del_fascicolo(db, fascicolo))
    preparato.nascosto = [
        f"{d.nome}, {n}" for d in documenti for n in testo_nascosto(d)
    ]
    if preparato.bloccato:
        raise InvioBloccato(preparato)
    arrivata, voce = chiedi(
        db,
        utente,
        fascicolo,
        modello,
        SISTEMA,
        preparato.testo,
        scopo=f"bozza: {tipo}",
        categorie=categorie(fascicolo, preparato),
        controllo=preparato.controllo(len(noti)),
    )
    salva_segnaposto(db, fascicolo, preparato.tabella)
    db.flush()  # il numero della voce del registro
    paragrafi = leggi_bozza(ricomponi(arrivata.testo, preparato.tabella))
    controlla(paragrafi, pagine, righe_delle_scadenze(scadenze))
    note = [f"Da completare: {d}" for d in da_completare(paragrafi)]
    note += [f"Da verificare: {d}" for d in da_verificare(paragrafi)]
    if tipo == "promemoria" and not scadenze:
        note.append(
            "Nessuna scadenza confermata: il promemoria non può dire entro "
            "quando, finché un avvocato non la conferma (lezione 19)."
        )
    elif tipo == "promemoria" and manca_la_scadenza(
        paragrafi, [s.scadenza for s in scadenze]
    ):
        note.append("Il promemoria non dice entro quando: manca la scadenza.")
    bozza = Bozza(
        fascicolo_id=fascicolo.id,
        tipo=tipo,
        paragrafi=json.dumps(
            [asdict(p) for p in paragrafi], ensure_ascii=False
        ),
        note=json.dumps(note, ensure_ascii=False),
        uso_ai_id=voce.id,
        preparata_da_id=utente.id,
    )
    db.add(bozza)
    registra_evento(db, utente, fascicolo, "bozza", tipo=tipo)
    db.commit()
    nome = avvocato.nome if avvocato else None
    return EsitoBozza(
        bozza, paragrafi, note, preparato, arrivata.testo, voce, nome
    )


# [/libro:prepara-bozza]


def paragrafi_di(bozza: Bozza) -> list[Paragrafo]:
    return [Paragrafo(**p) for p in json.loads(bozza.paragrafi)]


def in_word(
    db: Session,
    bozza: Bozza,
    percorso: Path,
    impaginazione: dict | None = None,
) -> Path:
    """La bozza come file Word: il riquadro con le note in cima, la
    provenienza nei commenti a margine, i dati da completare in giallo."""
    fascicolo = db.get(Fascicolo, bozza.fascicolo_id)
    voce = db.get(UsoAI, bozza.uso_ai_id)
    paragrafi = paragrafi_di(bozza)
    note = json.loads(bozza.note) + [
        f"Paragrafo {n}: {problema}"
        for n, p in enumerate(paragrafi, start=1)
        for problema in p.problemi
    ]
    giorno = bozza.preparata_il.date().isoformat()
    intestazione = (
        f"BOZZA · fascicolo {fascicolo.codice} · {bozza.tipo} · preparata "
        f"da Minuta il {giorno} con il modello {voce.modello}. Non è un "
        "atto: va riletta, corretta e firmata da un avvocato."
    )
    return word.scrivi(
        in_markdown(intestazione, paragrafi, note), percorso, impaginazione
    )


# [libro:approva-bozza]
def approva_bozza(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    bozza: Bozza,
    file: Path | None = None,
    forza: bool = False,
) -> list[str]:
    """Nessun testo entra in un atto o arriva al cliente senza
    l'approvazione di un avvocato. Si approva il file corretto in Word,
    letto come se le revisioni fossero accettate; se restano parti di
    Minuta, solo con una forzatura, che il registro conserva."""
    if utente.ruolo != "avvocato":
        raise BozzaRifiutata("Una bozza la approva un avvocato.")
    if bozza.approvata_da_id is not None:
        raise BozzaRifiutata("La bozza è già approvata.")
    if file is not None:
        testo = "\n".join(word.leggi(file))
        residui = word.residui(file)
    else:
        testo = "\n\n".join(p.testo for p in paragrafi_di(bozza))
        residui = word.residui_nel_testo(testo)
    if residui and not forza:
        raise BozzaRifiutata(
            f"Restano parti della bozza: {'; '.join(residui)}. Correggila e "
            "approva il file, oppure forza: la forzatura resta nel registro."
        )
    bozza.approvata_da_id, bozza.approvata_il = utente.id, adesso()
    bozza.testo_approvato = testo
    bozza.forzatura = (
        json.dumps(residui, ensure_ascii=False) if residui else None
    )
    registra_evento(
        db,
        utente,
        fascicolo,
        "approvazione",
        bozza=bozza.id,
        forzatura=residui,
    )
    db.commit()
    return residui


# [/libro:approva-bozza]
