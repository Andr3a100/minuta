"""Le regole del lavoro sui fascicoli: campi ammessi e passaggi di stato.

Qui non c'è niente di web né di database. Sono regole pure: si leggono
come una specifica e si provano con test semplici.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

CODICE = re.compile(r"[0-9]{4}-[0-9]{3}")
CLIENTE_MAX = 120
OGGETTO_MAX = 200

ETICHETTE_STATI = {
    "aperto": "Aperto",
    "in_studio": "In studio",
    "deciso": "Deciso",
    "chiuso": "Chiuso",
}
ETICHETTE_RUOLI = {
    "avvocato": "Avvocato",
    "praticante": "Praticante",
    "segreteria": "Segreteria",
}
ETICHETTE_MATERIE = {
    "civile": "Civile",
    "tributario": "Tributario",
    "penale": "Penale",
}

# Chi apre un fascicolo: chi lo registra in segreteria, o un avvocato.
APRONO = ("avvocato", "segreteria")

# [libro:passaggi]
# Per ogni passaggio di stato: chi può farlo e come si chiama il pulsante.
# Studiare, decidere, chiudere: i verbi della lezione 5.
PASSAGGI = {
    ("aperto", "in_studio"): (
        ("avvocato", "praticante"),
        "Comincia lo studio",
    ),
    ("in_studio", "deciso"): (("avvocato",), "Segna la decisione"),
    ("deciso", "chiuso"): (("avvocato",), "Chiudi"),
    ("chiuso", "aperto"): (("avvocato",), "Riapri"),
}


def passaggio_previsto(attuale: str, nuovo: str) -> bool:
    return (attuale, nuovo) in PASSAGGI


def passaggio_ammesso(attuale: str, nuovo: str, ruolo: str) -> bool:
    regola = PASSAGGI.get((attuale, nuovo))
    return regola is not None and ruolo in regola[0]


def azioni_disponibili(attuale: str, ruolo: str) -> list[tuple[str, str]]:
    """I passaggi che questo ruolo può fare da questo stato."""
    return [
        (nuovo, etichetta)
        for (da, nuovo), (ruoli, etichetta) in PASSAGGI.items()
        if da == attuale and ruolo in ruoli
    ]


# [/libro:passaggi]


class ValidationErrors(Exception):
    """Uno o più campi non rispettano le regole."""

    def __init__(self, errori: dict[str, str]):
        super().__init__("dati non validi")
        self.errori = errori


# [libro:campi-fascicolo]
def campi_fascicolo(
    modulo: Mapping[str, str], avvocati: set[int], praticanti: set[int]
) -> dict:
    """Restituisce solo i campi ammessi, già controllati e convertiti."""
    errori: dict[str, str] = {}
    codice = modulo.get("codice", "").strip()
    cliente = modulo.get("cliente", "").strip()
    materia = modulo.get("materia", "").strip()
    oggetto = modulo.get("oggetto", "").strip()

    if not CODICE.fullmatch(codice):
        errori["codice"] = "Il codice ha la forma anno-numero: 2026-041."
    if not cliente:
        errori["cliente"] = "Il cliente è obbligatorio."
    elif len(cliente) > CLIENTE_MAX:
        errori["cliente"] = f"Il cliente supera {CLIENTE_MAX} caratteri."
    if materia not in ETICHETTE_MATERIE:
        errori["materia"] = "Scegli la materia: civile, tributario, penale."
    if not oggetto:
        errori["oggetto"] = "L'oggetto è obbligatorio."
    elif len(oggetto) > OGGETTO_MAX:
        errori["oggetto"] = f"L'oggetto supera {OGGETTO_MAX} caratteri."

    avvocato_id = numero(modulo.get("avvocato_id", ""))
    if avvocato_id not in avvocati:
        errori["avvocato_id"] = "Scegli un avvocato attivo."
    praticante_id = numero(modulo.get("praticante_id", ""))
    if modulo.get("praticante_id", "").strip() and (
        praticante_id not in praticanti
    ):
        errori["praticante_id"] = "Scegli un praticante attivo, o nessuno."

    if errori:
        raise ValidationErrors(errori)
    return {
        "codice": codice,
        "cliente": cliente,
        "materia": materia,
        "oggetto": oggetto,
        "avvocato_id": avvocato_id,
        "praticante_id": praticante_id,
    }


# [/libro:campi-fascicolo]


def numero(valore: str) -> int | None:
    valore = valore.strip()
    # isascii() evita cifre come "²", che isdigit() accetta ma int() no.
    if valore.isascii() and valore.isdigit() and len(valore) <= 9:
        return int(valore)
    return None


def leggi_versione(valore: str) -> int | None:
    """La versione letta dal modulo; None se non è un numero valido."""
    n = numero(valore)
    return n if n is not None and n >= 1 else None
