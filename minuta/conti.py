"""I conti della lezione 3: quanto costa un fascicolo, quanto costa l'AI.

Funzioni piccole, perché ogni numero stampato nel libro venga da qui e una
prova lo tenga fermo. I valori di Studio Meridiana sono inventati.
"""

from __future__ import annotations


def ore(fascicoli_al_mese: float, minuti: float) -> float:
    """Le ore al mese di un'attività che dura «minuti» per fascicolo."""
    return fascicoli_al_mese * minuti / 60


def saldi(avvio: float, gestione_annua: float, beneficio_annuo: float, anni: int) -> list[float]:
    """Il saldo cumulato alla fine di ogni anno: si paga l'avvio, poi ogni anno
    entra il beneficio ed esce la gestione."""
    saldo, risultato = -avvio, []
    for _ in range(anni):
        saldo += beneficio_annuo - gestione_annua
        risultato.append(round(saldo, 2))
    return risultato


def anno_di_pareggio(elenco: list[float]) -> int | None:
    """Il primo anno chiuso in attivo, contando da 1; None se non arriva."""
    for anno, saldo in enumerate(elenco, start=1):
        if saldo >= 0:
            return anno
    return None
