import json

from minuta import search
from percorsi import RADICE

DOMANDE = json.loads((RADICE / "tests/domande.json").read_text("utf-8"))


def test_i_precedenti_giusti_escono_in_cima(db):
    primo = sum(search.cerca(db, d["domanda"], quanti=1)[0].atto_id == d["atteso"]
                for d in DOMANDE)
    tre = sum(d["atteso"] in [r.atto_id for r in search.cerca(db, d["domanda"], quanti=3)]
              for d in DOMANDE)
    # Misurato il 5 ottobre 2026: 9 su 10 al primo posto, 10 su 10 fra i primi tre.
    # La domanda sulla diffida trova prima l'atto 02, che parla di una lettera di
    # messa in mora: con il filtro per tipo torna al primo posto.
    assert primo >= 9
    assert tre == 10


def test_il_filtro_per_tipo(db):
    domanda = "lettera di diffida e messa in mora con termine di quindici giorni"
    assert search.cerca(db, domanda, tipo="diffida")[0].atto_id == "09"


def test_i_numeri_non_contano():
    assert search.termini("stagione 2025/2026, fattura n. 455") == ["stagione", "fattura"]


def test_filtro_per_autore(db):
    risultati = search.cerca(db, "interessi moratori transazione commerciale", autore="dini")
    assert risultati and all(r.autore == "dini" for r in risultati)
