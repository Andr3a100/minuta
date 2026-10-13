"""Il glossario del fascicolo (lezione 29): le parole che per un fascicolo
dicono la stessa cosa, decise dall'avvocato.

Minuta sceglie le pagine confrontando le radici delle parole (lezione 21):
«forno» e «fornitura» non s'incontrano, e accorciare le radici fa partire
pagine che non c'entrano (lezione 27). In Ristorazione Collinare, però, la
fornitura è la cucina, e il forno ne fa parte: lo sa chi conosce il caso, e
lo scrive nel glossario. La domanda porta con sé le parole equivalenti
soltanto per la scelta delle pagine; al modello parte com'era.
"""

from __future__ import annotations

from .domande import MASSIMO_PASSI, Passo, parole, scegli_passi


# [libro:scegli-con-glossario]
def scegli_con_glossario(
    domanda: str,
    documenti: dict[str, list[str]],
    glossario: dict[str, list[str]],
) -> list[Passo]:
    """Le pagine della lezione 21, più quelle con una parola che il
    glossario dà come equivalente a una della domanda: l'avvocato l'ha
    deciso, e partono per prime. Sempre al massimo tre."""
    cercate = parole(domanda)
    equivalenti = set()
    for parola, altre in glossario.items():
        if parole(parola) & cercate:
            equivalenti |= parole(" ".join(altre))
    scelti = [
        Passo(nome, numero, testo, len(equivalenti & parole(testo)))
        for nome, pagine in documenti.items()
        for numero, testo in enumerate(pagine, start=1)
        if equivalenti & parole(testo)
    ][:MASSIMO_PASSI]
    presi = {(p.documento, p.pagina) for p in scelti}
    altri = [
        p
        for p in sorted(
            scegli_passi(domanda, documenti), key=lambda p: -p.punti
        )
        if (p.documento, p.pagina) not in presi
    ]
    scelti += altri[: MASSIMO_PASSI - len(scelti)]
    ordine = list(documenti)
    return sorted(scelti, key=lambda p: (ordine.index(p.documento), p.pagina))


# [/libro:scegli-con-glossario]
