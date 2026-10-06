"""Le misure di partenza della lezione 2: media e mediana, fatte a mano.

Sono i conti che l'avvocato fa su dieci fascicoli prima di cambiare
qualunque cosa. Stanno nel laboratorio perché i numeri stampati nel libro
vengano da qui, e una prova li tenga fermi.
"""

from __future__ import annotations

from statistics import mean, median


def riassunto(valori: list[float]) -> tuple[float, float]:
    """La media e la mediana di una serie di misure."""
    if not valori:
        raise ValueError("servono delle misure")
    return round(mean(valori), 2), round(median(valori), 2)


def quota(sono: int, su: int) -> int:
    """Una percentuale intera: 3 fascicoli su 5 fanno 60."""
    return round(100 * sono / su)
