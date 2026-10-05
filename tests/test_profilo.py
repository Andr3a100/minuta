import json
import re


def test_i_due_stili_sono_riconosciuti(profilo):
    sarti, dini = profilo["autori"]["sarti"], profilo["autori"]["dini"]
    assert sarti["intestazione"] == "TRIBUNALE ORDINARIO DI MODENA"
    assert dini["intestazione"] == "TRIBUNALE DI MODENA"
    assert sarti["titolo"] == "RICORSO PER DECRETO INGIUNTIVO"
    assert dini["titolo"] == "Ricorso per ingiunzione di pagamento"
    assert sarti["sezioni"].endswith("procura")
    assert sarti["parole_per_frase"] > dini["parole_per_frase"]
    assert any("come sopra rappresentata e difesa" in f for f in sarti["formule_proprie"])
    assert any("Si chiede al Tribunale di ingiungere" in f for f in dini["formule_proprie"])


def test_ogni_formula_dice_da_quali_atti_viene(profilo):
    for dati in profilo["autori"].values():
        assert all(len(ids) >= 2 for ids in dati["formule_proprie"].values())


def test_il_profilo_non_contiene_dati_personali(profilo, oracolo):
    # Le chiavi («sarti», «dini») sono identificativi interni e non vanno al
    # modello; il contenuto del profilo, che ci va, non deve avere dati personali.
    testo = json.dumps(list(profilo["autori"].values()), ensure_ascii=False).lower()
    sensibili = {s.lower() for valori in oracolo.values() for s in valori}
    assert [s for s in sensibili if re.search(rf"(?<!\w){re.escape(s)}(?!\w)", testo)] == []
