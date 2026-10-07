"""Che cosa parte verso il modello (lezione 17).

La prima prova mantiene la promessa della lezione 4: il paragrafo con il
dipendente che nessuno aveva messo in elenco non deve più passare.
"""

from __future__ import annotations

import pytest
from percorsi import RADICE

from minuta import archive
from minuta.invio import (
    nomi_rimasti,
    prepara,
    ricomponi,
    salute,
    segnaposto_sconosciuti,
)
from minuta.pseudonym import Pseudonimizzatore

PARAGRAFO = (RADICE / "esempi" / "04-paragrafo.txt").read_text("utf-8")
NOTI = {"Alessandro Riva": "PERSONA", "Logistica Riva S.r.l.": "SOGGETTO"}
CONFIG = archive.carica_config(RADICE / "config" / "studio.json")
ATTI = sorted((RADICE / "archivio" / "pdf").glob("*.pdf"))


# [libro:prova-lezione-4]
def test_il_dipendente_fuori_elenco_non_passa_piu():
    # L'esempio della lezione 4: il pilota lo lasciava partire.
    preparato = prepara(PARAGRAFO, NOTI)
    assert preparato.nomi == ["Marco Bellini"]
    assert preparato.bloccato
    # Messo in elenco, il dipendente diventa un segnaposto, sempre lo stesso.
    completo = prepara(PARAGRAFO, {**NOTI, "Marco Bellini": "PERSONA"})
    assert not completo.bloccato
    assert "Bellini" not in completo.testo
    assert completo.testo.count("[PERSONA_2]") == 2


# [/libro:prova-lezione-4]


def test_i_dati_sulla_salute_si_segnalano_senza_bloccare():
    completo = prepara(PARAGRAFO, {**NOTI, "Marco Bellini": "PERSONA"})
    assert completo.salute == ["frattura", "prognosi", "ricoverato"]
    assert not completo.bloccato


def test_il_nome_di_battesimo_di_un_altro_non_tocca_nessuno():
    # «Marco» di Marco Dini non deve coprire metà di Marco Bellini.
    noti = {**NOTI, "Marco Dini": "PERSONA"}
    preparato = prepara(PARAGRAFO, noti)
    assert "Marco Bellini" in preparato.testo
    assert preparato.nomi == ["Marco Bellini"]


def test_mezzo_nome_scoperto_si_trova():
    assert nomi_rimasti("Alessandro [SOGGETTO_1], legale rappresentante") == [
        "Alessandro"
    ]
    assert nomi_rimasti("Il [PERSONA_1] e l'avv. [PERSONA_2]") == []


def test_i_comuni_non_sono_persone():
    testo = "sede in Castelfranco Emilia, via Roma, e a Castelnuovo Rangone"
    assert nomi_rimasti(testo) == []
    assert nomi_rimasti("il sig. Mario Carpi, di Carpi") == ["Mario Carpi"]


@pytest.mark.parametrize("percorso", ATTI, ids=[p.stem[:12] for p in ATTI])
def test_nessun_falso_allarme_sugli_atti_dell_archivio(percorso):
    atto = archive.leggi_atto(percorso, CONFIG["avvocati"])
    preparato = prepara(atto.testo, {CONFIG["studio"]: "STUDIO"})
    assert preparato.nomi == []
    assert preparato.fughe == []


def test_i_segnaposto_restano_gli_stessi_fra_un_invio_e_l_altro():
    primo = prepara(PARAGRAFO, {**NOTI, "Marco Bellini": "PERSONA"})
    secondo = prepara(
        "Il sig. Bellini lavorava per Logistica Riva S.r.l.",
        {**NOTI, "Marco Bellini": "PERSONA"},
        primo.tabella,
    )
    segno = next(s for s, v in primo.tabella.items() if v == "Marco Bellini")
    assert segno in secondo.testo
    assert secondo.tabella[segno] == "Marco Bellini"


def test_la_risposta_torna_con_i_nomi_e_gli_inventati_si_vedono():
    completo = prepara(PARAGRAFO, {**NOTI, "Marco Bellini": "PERSONA"})
    risposta = "[PERSONA_2] lavorava per [SOGGETTO_1]; [PERSONA_9] no."
    assert ricomponi(risposta, completo.tabella).startswith(
        "Marco Bellini lavorava per Logistica Riva S.r.l.;"
    )
    assert segnaposto_sconosciuti(risposta, completo.tabella) == [
        "[PERSONA_9]"
    ]


def test_il_pilota_conserva_i_nomi_di_battesimo():
    # Le bozze del pilota ricompongono il testo identico: lì si nasconde
    # anche il nome da solo, come prima.
    pseudonimi = Pseudonimizzatore(noti={"Giorgio Taddei": "PERSONA"})
    assert "Giorgio" not in pseudonimi.nascondi("Giorgio ha firmato.")


def test_salute_riconosce_le_parole_e_non_altro():
    assert salute("ricoverata con diagnosi di frattura") == [
        "diagnosi",
        "frattura",
        "ricoverata",
    ]
    assert salute("il ricorso per decreto ingiuntivo") == []
