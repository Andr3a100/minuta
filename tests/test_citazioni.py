from minuta import citations


def test_estrazione_dall_atto(atti):
    chiavi = [c.chiave for c in citations.estrai(atti["01-2019-sarti-imballaggi-bassi"].testo)]
    assert chiavi == ["c.p.c. art. 633", "c.p.c. art. 634", "d.lgs. 231/2002 art. 5",
                      "d.lgs. 231/2002 art. 4", "d.lgs. 231/2002 art. 6", "c.p.c. art. 641",
                      "d.p.r. 115/2002 art. 14"]


def test_rinvii_brevi_al_decreto_appena_citato():
    testo = "interessi dell'art. 5 del D.Lgs. 231/2002 dalla scadenza (art. 4), oltre (art. 6)"
    assert [c.chiave for c in citations.estrai(testo)] == [
        "d.lgs. 231/2002 art. 5", "d.lgs. 231/2002 art. 4", "d.lgs. 231/2002 art. 6"]


def test_il_massimario_dello_studio_e_verificato(massimario):
    # Le undici norme citate nell'archivio, aperte sul testo vigente di
    # Normattiva il 5 ottobre 2026 (verbali/massimario-2026-10-05.txt), e la
    # sentenza C-585/20 della Corte di giustizia, letta sul testo ufficiale.
    assert len(massimario.ammesse()) == 12


def test_una_sentenza_inventata_resta_da_verificare(massimario):
    stati = citations.controlla("come da Cass. civ., sez. II, 15 maggio 2023, n. 99999", massimario)
    assert stati[0]["stato"].startswith("da verificare: sentenza")


def test_una_norma_fuori_dal_massimario(massimario):
    stati = citations.controlla("ai sensi dell'art. 2043 c.c.", massimario)
    assert stati[0]["stato"].startswith("da verificare: norma")


def test_indirizzi_normattiva_degli_allegati():
    assert citations.indirizzo_normattiva("c.c. art. 1224").endswith(";262:2~art1224")
    assert citations.indirizzo_normattiva("c.p.c. art. 642").endswith(";1443:1~art642")


def test_le_cause_europee_si_riconoscono(massimario):
    stati = citations.controlla("come chiarito dalla Corte di giustizia nella causa C-585/20", massimario)
    assert stati == [{"citazione": "C-585/20", "chiave": "cgue C-585/20", "stato": "verificata"}]
