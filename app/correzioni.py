"""Le correzioni dell'avvocato (lezione 26): Minuta impara senza addestrare
nessun modello.

Quando un avvocato approva un atto, Minuta confronta la bozza con il testo
approvato e mette ogni modifica nel suo tipo: un dato completato, un dato
cambiato, una correzione di stile, un passaggio riscritto. Solo le
correzioni di stile si conservano, con i dati e i nomi già tolti: parlano
di come scrive l'avvocato, non dei suoi clienti. Una correzione fatta in due
atti di fascicoli diversi diventa una regola; in un atto solo può essere un
caso. Le regole vanno nella richiesta al modello e si controllano sulla
bozza. L'avvocato può respingere una correzione, che allora non diventa mai
una regola.

Gli atti approvati non entrano nel profilo dello stile, che si calcola
soltanto dagli atti dell'archivio: fra gli esempi restano gli atti scritti
senza Minuta, e lo stile non scivola verso quello del modello.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta import learning

from .db import (
    Bozza,
    Correzione,
    CorrezioneRespinta,
    Fascicolo,
    Utente,
    adesso,
)
from .invio import noti_del_fascicolo
from .web import registra_evento


class CorrezioneRifiutata(Exception):
    """L'operazione sulle correzioni non è ammessa: il messaggio dice
    perché."""


# [libro:registra-correzioni]
def registra_correzioni(
    db: Session,
    utente: Utente,
    fascicolo: Fascicolo,
    bozza: Bozza,
    testo_della_bozza: str,
) -> list[dict]:
    """Le modifiche dell'avvocato fra la bozza e il testo approvato. Si
    contano tutte; si conservano le correzioni di stile degli atti, non
    quelle di un promemoria per il cliente, che ha un altro registro."""
    modifiche = learning.confronta(
        testo_della_bozza,
        bozza.testo_approvato,
        noti_del_fascicolo(db, fascicolo),
    )
    if bozza.tipo != "promemoria":
        for m in modifiche:
            if m["tipo"] == "stile":
                db.add(
                    Correzione(
                        avvocato_id=utente.id,
                        bozza_id=bozza.id,
                        fascicolo_id=fascicolo.id,
                        prima=m["prima"],
                        dopo=m["dopo"],
                        contesto=m["contesto"],
                    )
                )
    return modifiche


# [/libro:registra-correzioni]


def voci_di(db: Session, avvocato: Utente) -> list[dict]:
    """Le correzioni di un avvocato, una voce per correzione, con i
    fascicoli in cui l'ha fatta: dalla più confermata, come il pilota."""
    respinte = {
        (r.prima, r.dopo): r.respinta_il
        for r in db.scalars(
            select(CorrezioneRespinta).where(
                CorrezioneRespinta.avvocato_id == avvocato.id
            )
        )
    }
    voci: dict[tuple[str, str], dict] = {}
    righe = db.execute(
        select(Correzione, Fascicolo.codice)
        .join(Fascicolo, Fascicolo.id == Correzione.fascicolo_id)
        .where(Correzione.avvocato_id == avvocato.id)
        .order_by(Correzione.id)
    )
    for correzione, codice in righe:
        chiave = (correzione.prima, correzione.dopo)
        voce = voci.setdefault(
            chiave,
            {
                "prima": correzione.prima,
                "dopo": correzione.dopo,
                "volte": 0,
                "fascicoli": [],
                "contesti": [],
            },
        )
        voce["volte"] += 1
        if codice not in voce["fascicoli"]:
            voce["fascicoli"].append(codice)
        if correzione.contesto and correzione.contesto not in voce["contesti"]:
            voce["contesti"].append(correzione.contesto)
        if chiave in respinte:
            voce["respinta"] = respinte[chiave].date().isoformat()
    return sorted(
        voci.values(),
        key=lambda v: (
            -len(v["fascicoli"]),
            -v["volte"],
            v["prima"],
            v["dopo"],
        ),
    )


def regole_di(db: Session, avvocato: Utente) -> list[dict]:
    """Le correzioni diventate regole: fatte in almeno due atti di
    fascicoli diversi, e mai respinte."""
    return [v for v in voci_di(db, avvocato) if learning.e_regola(v)]


def stato_di(voce: dict) -> str:
    if voce.get("respinta"):
        return f"respinta il {voce['respinta']}"
    return "regola" if learning.e_regola(voce) else "osservata"


def come_si_legge(voce: dict) -> str:
    """«somma» → «sorte capitale»: una correzione in una riga."""
    prima = f"«{voce['prima']}»" if voce["prima"] else "niente"
    dopo = f"«{voce['dopo']}»" if voce["dopo"] else "niente"
    return f"{prima} → {dopo}"


def respingi(db: Session, utente: Utente, numero: int) -> dict:
    """L'avvocato dice che una sua correzione non va generalizzata."""
    if utente.ruolo != "avvocato":
        raise CorrezioneRifiutata(
            "Una correzione la respinge l'avvocato che l'ha fatta."
        )
    voci = voci_di(db, utente)
    if not 1 <= numero <= len(voci):
        raise CorrezioneRifiutata(
            f"Fra le correzioni di {utente.nome} non c'è la n. {numero}."
        )
    voce = voci[numero - 1]
    if voce.get("respinta"):
        raise CorrezioneRifiutata(f"La correzione n. {numero} è già respinta.")
    quando = adesso()
    db.add(
        CorrezioneRespinta(
            avvocato_id=utente.id,
            prima=voce["prima"],
            dopo=voce["dopo"],
            respinta_il=quando,
        )
    )
    registra_evento(
        db,
        utente,
        None,
        "correzione_respinta",
        prima=voce["prima"],
        dopo=voce["dopo"],
    )
    db.commit()
    voce["respinta"] = quando.date().isoformat()
    return voce
