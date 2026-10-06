import pymupdf

from minuta import nascosti


def test_trova_il_testo_che_non_si_vede_e_lascia_quello_visibile(tmp_path):
    percorso = tmp_path / "atto.pdf"
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 100), "Testo visibile del ricorso.", fontsize=11)
    pagina.insert_text((72, 130), "Istruzione in bianco.", fontsize=11, color=(1, 1, 1))
    pagina.insert_text((72, 160), "Istruzione minuscola.", fontsize=1)
    pagina.insert_text((72, 2000), "Istruzione fuori pagina.", fontsize=11)
    documento.save(percorso)
    trovati = {n.testo: n.motivo for n in nascosti.testo_nascosto(percorso)}
    assert trovati == {"Istruzione in bianco.": "testo bianco",
                       "Istruzione minuscola.": "corpo minuscolo",
                       "Istruzione fuori pagina.": "fuori dalla pagina"}


def test_un_documento_pulito_non_ha_testo_nascosto(tmp_path):
    percorso = tmp_path / "pulito.pdf"
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 100), "Solo testo visibile.", fontsize=11)
    documento.save(percorso)
    assert nascosti.testo_nascosto(percorso) == []
