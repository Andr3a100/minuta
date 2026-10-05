import re

import pytest

from minuta.leaks import fughe
from minuta.pseudonym import Pseudonimizzatore, segnaposto_estranei
from conftest import RADICE

FILE = sorted(p.stem for p in (RADICE / "archivio/pdf").glob("*.pdf"))


@pytest.mark.parametrize("file", FILE)
def test_nessuna_fuga(atti, oracolo, config, file):
    p = Pseudonimizzatore(noti={config["studio"]: "STUDIO"})
    nascosto = p.nascondi(atti[file].testo)
    assert fughe(nascosto, oracolo[file]) == []


@pytest.mark.parametrize("file", FILE)
def test_ricomposizione_identica(atti, config, file):
    p = Pseudonimizzatore(noti={config["studio"]: "STUDIO"})
    assert p.ricomponi(p.nascondi(atti[file].testo)) == atti[file].testo


@pytest.mark.parametrize("file", FILE)
def test_nessuna_parola_comune_nascosta(atti, oracolo, config, file):
    """Si nasconde solo ciò che identifica qualcuno, non «procura» o «fattura»."""
    p = Pseudonimizzatore(noti={config["studio"]: "STUDIO"})
    p.nascondi(atti[file].testo)
    attesi = [s.lower() for s in oracolo[file]]
    eccessi = [v for v in p.tabella.values()
               if not any(a in v.lower() or v.lower() in a for a in attesi)]
    assert eccessi == []


def test_un_nome_non_attraversa_l_a_capo():
    testo = "È autentica. Avv. Elena Sarti\nPROCURA ALLE LITI\ngiusta procura in calce"
    nascosto = Pseudonimizzatore().nascondi(testo)
    assert "giusta procura in calce" in nascosto
    assert "Sarti" not in nascosto


def test_segnaposto_generici_per_il_profilo():
    testo = "difesa dall'Avv. Marco Dini (C.F. DNIMRC80H03F257B), PEC marco.dini@pec.example"
    nascosto = Pseudonimizzatore(generico=True).nascondi(testo)
    assert nascosto == "difesa dall'Avv. [PERSONA] (C.F. [CF]), PEC [EMAIL]"


def test_i_segnaposto_degli_esempi_si_riconoscono():
    assert segnaposto_estranei("a [SOGGETTO_1] e [E1_SOGGETTO_2]") == ["[E1_SOGGETTO_2]"]


def test_la_prova_delle_fughe_trova_i_codici():
    testo = "C.F. RSSMRA80A01F257X, IBAN IT40S0542811101000000123456, a@b.example, 03456780361"
    assert len(fughe(testo)) == 4
    assert fughe("[PERSONA_1] ha pagato [IMPORTO]") == []
    assert re.search("Bassi", " ".join(fughe("la ditta Bassi", ["Bassi"])))
