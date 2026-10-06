# Copiato senza modifiche dalla risposta di gpt-6.1-sol del 7 ottobre 2026
# (verbali/L13-errore-deliberato-2026-10-07.json del libro), lezione 13.

from datetime import date, datetime, timedelta


def _pasqua(anno: int) -> date:
    """Calcola la Pasqua gregoriana."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese, resto = divmod(h + l - 7 * m + 114, 31)
    return date(anno, mese, resto + 1)


def _festivo(giorno: date) -> bool:
    festivita = {
        (1, 1),    # Capodanno
        (1, 6),    # Epifania
        (4, 25),   # Liberazione
        (5, 1),    # Festa del lavoro
        (6, 2),    # Festa della Repubblica
        (8, 15),   # Ferragosto
        (11, 1),   # Ognissanti
        (12, 8),   # Immacolata
        (12, 25),  # Natale
        (12, 26),  # Santo Stefano
    }

    # San Francesco è festività nazionale dal 2026.
    if giorno.year >= 2026:
        festivita.add((10, 4))

    return (
        giorno.weekday() == 6
        or (giorno.month, giorno.day) in festivita
        or giorno == _pasqua(giorno.year) + timedelta(days=1)
    )


def scadenza_opposizione(notifica: date) -> date:
    """
    Ultimo giorno del termine ordinario di 40 giorni.

    Presuppone l'applicabilità della sospensione feriale.
    Non gestisce termini speciali o festività locali.
    """
    if not isinstance(notifica, date) or isinstance(notifica, datetime):
        raise TypeError("notifica deve essere un datetime.date")

    if notifica < date(2015, 1, 1):
        raise ValueError("Sono supportate soltanto notifiche dal 2015")

    giorno = notifica
    giorni_computati = 0
    un_giorno = timedelta(days=1)

    # Il giorno della notifica non conta; agosto è sospeso.
    # Sabati e festivi intermedi, invece, contano.
    while giorni_computati < 40:
        giorno += un_giorno
        if giorno.month != 8:
            giorni_computati += 1

    # Proroga della scadenza, rispettando anche la sospensione feriale.
    while giorno.month == 8 or giorno.weekday() == 5 or _festivo(giorno):
        giorno += un_giorno

    return giorno
