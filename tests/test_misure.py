"""I numeri della lezione 2, rifatti dal laboratorio."""

from minuta.misure import quota, riassunto

# Studio Meridiana, cinque fascicoli di settembre 2026 (inventati).
STUDIO = [95, 140, 210, 60, 125]
STESURA = [120, 90, 150, 80, 110]


def test_media_e_mediana_dello_studio():
    assert riassunto(STUDIO) == (126, 125)
    assert riassunto(STESURA) == (110, 110)


def test_il_caso_che_sposta_la_media():
    # Un sesto fascicolo penale: due giornate di lavoro sugli atti d'indagine.
    assert riassunto(STUDIO + [960]) == (265, 132.5)


def test_completezza_e_errori():
    assert quota(2, 5) == 40  # scadenze annotate con norma e data di lettura
    assert quota(3, 5) == 60  # fascicoli con almeno un errore trovato in revisione


def test_il_volume_del_mese():
    # Trenta fascicoli al mese, al tempo medio di studio: le ore della lezione 3.
    assert 30 * riassunto(STUDIO)[0] / 60 == 63
