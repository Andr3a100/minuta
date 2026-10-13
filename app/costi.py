"""I costi del fornitore (lezione 31): quanto si spende, e un tetto.

La spesa è quella del registro dell'uso dell'AI, voce per voce, con i
prezzi del listino e le condizioni del contratto. Il tetto del mese ferma
le richieste prima che partano: quando la spesa lo raggiunge, e quando il
modello non ha un prezzo nel listino, perché una spesa che non si sa
stimare non si sa nemmeno fermare. Un tetto di zero ferma tutto: è il modo
di chiudere il rubinetto, per esempio se una chiave è stata compromessa.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from minuta.model import Modello, Risposta

from .db import Fascicolo, UsoAI, Utente, make_engine, make_session_factory
from .registro import RichiestaNonAmmessa, ha_prezzo


def mese_di(quando: datetime) -> str:
    return quando.strftime("%Y-%m")


def voci_del_mese(db: Session, mese: str) -> list[UsoAI]:
    return [v for v in db.scalars(select(UsoAI)) if mese_di(v.quando) == mese]


def spesa_del_mese(db: Session, mese: str) -> float:
    return sum(v.costo_usd or 0 for v in voci_del_mese(db, mese))


# [libro:tetto]
class ModelloConTetto:
    """Il modello del fornitore, con il tetto della spesa del mese davanti.
    Il controllo viene prima della richiesta: oltre il tetto non parte."""

    def __init__(self, modello: Modello, tetto: float, database_url: str):
        self.modello = modello
        self.nome = modello.nome
        self.tetto = tetto
        self.database_url = database_url

    def scrivi(self, sistema: str, richiesta: str) -> Risposta:
        finto = self.nome.startswith("finto")
        if not finto and not ha_prezzo(self.nome):
            raise RichiestaNonAmmessa(
                f"Il listino non ha il prezzo di {self.nome}: con un tetto "
                "alla spesa, la richiesta non parte (config/prezzi.json)."
            )
        engine = make_engine(self.database_url)
        try:
            with make_session_factory(engine)() as db:
                spesa = spesa_del_mese(db, mese_di(datetime.now(UTC)))
        finally:
            engine.dispose()
        if spesa >= self.tetto:
            raise RichiestaNonAmmessa(
                f"Tetto del mese raggiunto: spesi {in_dollari(spesa)} su "
                f"{in_dollari(self.tetto)}. La richiesta non parte."
            )
        return self.modello.scrivi(sistema, richiesta)


# [/libro:tetto]


def in_dollari(cifra: float) -> str:
    intero, decimali = f"{cifra:,.2f}".split(".")
    return f"{intero.replace(',', '.')},{decimali} dollari"


def riepilogo(db: Session, mese: str) -> dict:
    """La spesa del mese per persona, per fascicolo e per modello, e le voci
    che il listino non sapeva stimare."""
    persone = {u.id: u.nome for u in db.scalars(select(Utente))}
    codici = {f.id: f.codice for f in db.scalars(select(Fascicolo))}
    gruppi = {
        "persona": defaultdict(float),
        "fascicolo": defaultdict(float),
        "modello": defaultdict(float),
    }
    voci = voci_del_mese(db, mese)
    for v in voci:
        costo = v.costo_usd or 0
        gruppi["persona"][persone.get(v.utente_id, "?")] += costo
        gruppi["fascicolo"][codici.get(v.fascicolo_id, "nessuno")] += costo
        gruppi["modello"][v.modello] += costo
    return {
        "mese": mese,
        "voci": len(voci),
        "senza_stima": sum(v.costo_usd is None for v in voci),
        "totale": sum(v.costo_usd or 0 for v in voci),
        **{k: dict(sorted(g.items())) for k, g in gruppi.items()},
    }
