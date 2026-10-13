"""Lo stile di ogni avvocato dai suoi atti (lezione 23): le formule con gli
atti da cui vengono, le norme da decidere, nessun dato personale."""

from __future__ import annotations

import json

from percorsi import RADICE

from minuta import documenti
from minuta.archivio import dati_dell_atto, leggi_indice, tipo_del_nome
from minuta.leaks import fughe
from minuta.stile import VUOTE, calcola, frasi, generico, ripetute, ripulita

ARCHIVIO = RADICE / "archivio"
AVVOCATI = [
    {"id": "sarti", "nome": "Elena Sarti"},
    {"id": "dini", "nome": "Marco Dini"},
]
STUDIO = {a["nome"]: "PERSONA" for a in AVVOCATI}
INDICE = leggi_indice(ARCHIVIO / "indice.csv")
RISERVATI = json.loads((ARCHIVIO / "entita.json").read_text("utf-8"))


def per_autore() -> dict[str, dict]:
    atti = {}
    for n, pdf in enumerate(sorted((ARCHIVIO / "pdf").glob("*.pdf")), 1):
        dati = dati_dell_atto(pdf, AVVOCATI)
        pagine = documenti.leggi(pdf.name, pdf.read_bytes()).pagine
        noti = STUDIO | {p: tipo_del_nome(p) for p in INDICE[pdf.stem]}
        testo = generico("\n".join(p.testo for p in pagine), noti)
        atti.setdefault(dati["autore"], {})[n] = (dati["tipo"], testo)
    return atti


ATTI = per_autore()
SARTI, DINI = calcola(ATTI["sarti"]), calcola(ATTI["dini"])


def test_due_avvocati_due_stili():
    assert SARTI.intestazione == "TRIBUNALE ORDINARIO DI MODENA"
    assert DINI.intestazione == "TRIBUNALE DI MODENA"
    assert SARTI.titolo == "RICORSO PER DECRETO INGIUNTIVO"
    assert DINI.titolo == "Ricorso per ingiunzione di pagamento"
    assert SARTI.parole_per_frase > DINI.parole_per_frase


# [libro:prova-stile]
def test_ogni_formula_dice_da_dove_viene_e_dove_manca():
    for profilo in (SARTI, DINI):
        for f in profilo.formule:
            assert len(f.atti) >= 2
            assert sorted(f.atti + f.manca) == profilo.atti


def test_la_norma_che_manca_nel_caso_del_consumatore_va_decisa():
    (interessi,) = [f for f in SARTI.formule if "transazione" in f.testo]
    assert "D.Lgs. 9 ottobre 2002, n. 231" in interessi.testo
    assert (interessi.atti, interessi.manca) == ([1, 5, 7, 10], [2])
    assert interessi.stato == "da decidere"


# [/libro:prova-stile]


def test_il_profilo_non_ha_dati_personali():
    for autore, profilo in (("sarti", SARTI), ("dini", DINI)):
        testo = json.dumps(
            [f.testo for f in profilo.formule], ensure_ascii=False
        )
        for n in profilo.atti:
            atto = sorted((ARCHIVIO / "pdf").glob("*.pdf"))[n - 1].stem
            riservati = [r for r in RISERVATI[atto] if r != "Studio Meridiana"]
            assert fughe(testo, riservati) == [], (autore, atto)


def test_le_abbreviazioni_non_chiudono_la_frase():
    testo = "Ai sensi dell'art. 14 del D.P.R. 115, n. 3. Poi segue: altro."
    assert frasi(testo) == [
        "Ai sensi dell'art. 14 del D.P.R. 115, n. 3.",
        "Poi segue: altro.",
    ]


def test_una_formula_contenuta_in_un_altra_non_si_ripete():
    testi = {
        1: "Per: [SOGGETTO] con sede legale nel comune di Modena, oggi.",
        2: "Per: [SOGGETTO] con sede legale nel comune di Modena, ieri.",
    }
    assert list(ripetute(testi)) == [
        "Per: [SOGGETTO] con sede legale nel comune di Modena"
    ]


def test_le_legature_tornano_lettere_e_i_bordi_si_puliscono():
    assert generico("la notiﬁca", {}) == "la notifica"
    assert any("dalla notifica del decreto" in f.testo for f in SARTI.formule)
    assert ripulita("al saldo, oltre spese e compensi del") == (
        "saldo, oltre spese e compensi"
    )


def test_nel_profilo_ne_doppioni_ne_bordi_vuoti():
    for profilo in (SARTI, DINI):
        for f in profilo.formule:
            assert f.testo.split()[-1].casefold() not in VUOTE
            for g in profilo.formule:
                dentro = f.testo != g.testo and f.testo in g.testo
                assert not (dentro and set(f.atti) <= set(g.atti))


def test_legge_conta_come_norma_solo_con_il_numero():
    procura = [f for f in SARTI.formule if "facoltà di legge" in f.testo]
    assert procura and not procura[0].norma
