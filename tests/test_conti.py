"""I numeri della lezione 3, rifatti dal laboratorio. Studio Meridiana è inventato,
tranne il costo di una bozza: otto bozze vere con gpt-6.1-sol, nel registro del
pilota, sono costate fra 0,0205 e 0,0268 dollari."""

from minuta.conti import anno_di_pareggio, ore, saldi

EURO_ORA = 60  # costo pieno orario ipotetico


def test_il_costo_dello_studio():
    assert ore(30, 126) == 63
    assert ore(30, 126) * EURO_ORA == 3780


def test_ore_liberate_e_revisione():
    assert ore(30, 30) == 15            # trenta minuti in meno di studio
    assert ore(30, 30 - 10) == 10       # meno dieci minuti per rileggere scheda e verifiche
    assert ore(30, 20) * EURO_ORA == 600


def test_il_tempo_di_chi_rilegge():
    assert ore(30, 10) == 5             # dieci minuti per fascicolo
    assert ore(30, 10) * EURO_ORA == 300


def test_il_costo_del_modello():
    per_fascicolo = 10 * 0.025          # dieci chiamate da circa 0,025 dollari
    assert round(per_fascicolo, 2) == 0.25
    assert round(30 * per_fascicolo, 2) == 7.5
    assert round(12 * 30 * per_fascicolo, 2) == 90


def test_le_alternative():
    assert 1500 + 300 == 1800           # procedura scritta e modelli
    assert 500 + 3600 == 4100           # prodotto in abbonamento
    assert 8000 + 1200 == 9200          # costruire Minuta


def test_il_ritorno_prudente():
    beneficio = ore(30, 20) / 2 * EURO_ORA * 12
    assert beneficio == 3600
    elenco = saldi(8000, 1200, beneficio, 4)
    assert elenco == [-5600, -3200, -800, 1600]
    assert anno_di_pareggio(elenco) == 4


def test_la_sensibilita():
    beneficio = round(ore(20, 10) / 2 * EURO_ORA * 12, 2)
    assert beneficio == 1200
    assert beneficio < 2 * 1200         # meno della gestione raddoppiata
    assert anno_di_pareggio(saldi(8000, 2400, beneficio, 10)) is None


def test_esercizio_risolto():
    beneficio = 12 * 50 * 0.5 * 12
    costi = 4000 + 100 * 12
    assert (beneficio, costi, beneficio - costi) == (3600, 5200, -1600)
