"""I conti dei fascicoli: le funzioni della lezione B5.

Sono gli stessi conti delle lezioni 2 e 3: la media e la mediana dei minuti
di studio, le ore al mese, il saldo anno per anno.
"""

import statistics


# [libro:riassunto]
def riassunto(minuti):
    """Quante misure, la loro media e la loro mediana.

    minuti: i minuti misurati, uno per fascicolo. Il risultato è un
    dizionario: ogni numero ha il suo nome.
    """
    if not minuti:
        raise ValueError("serve almeno una misura")
    return {
        "misure": len(minuti),
        "media": statistics.mean(minuti),
        "mediana": statistics.median(minuti),
    }


# [/libro:riassunto]


# [libro:ore]
def ore(fascicoli_al_mese, minuti):
    """Le ore al mese di un'attività che dura «minuti» per fascicolo."""
    if fascicoli_al_mese < 0:
        raise ValueError("i fascicoli non possono essere negativi")
    return fascicoli_al_mese * minuti / 60


# [/libro:ore]


# [libro:saldi]
def saldi(avvio, gestione_annua, beneficio_annuo, anni):
    """Il saldo alla fine di ogni anno: si paga l'avvio, poi ogni anno
    entra il beneficio ed esce il costo di gestione."""
    saldo = -avvio
    risultato = []
    for _ in range(anni):
        saldo = saldo + beneficio_annuo - gestione_annua
        risultato.append(saldo)
    return risultato


# [/libro:saldi]
