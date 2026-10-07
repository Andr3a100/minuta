import hashlib
import json
import shutil

import pytest
from percorsi import RADICE

from minuta import __main__ as comandi
from minuta import archive, draft, learning, search
from minuta.model import ModelloFinto


def bozza_e_firmato(db, fascicolo, config, profilo, massimario, tmp_path):
    """Una bozza del modello finto e l'atto che l'avvocato firma dopo averla corretta."""
    bozza = draft.prepara(db, fascicolo, config, profilo, massimario, ModelloFinto(),
                          tmp_path / "registro")
    testo = bozza.testo
    firmato = (testo.replace("la somma di euro", "la sorte capitale di euro")
                    .replace("[DA COMPLETARE: luogo e data]", "Modena, 20 ottobre 2026,")
                    .replace("9.960,50", "9.960,00"))
    return testo, firmato


def test_le_modifiche_hanno_il_loro_tipo(db, fascicolo, config, profilo, massimario, tmp_path):
    testo, firmato = bozza_e_firmato(db, fascicolo, config, profilo, massimario, tmp_path)
    modifiche = learning.confronta(testo, firmato, draft.sensibili_del_fascicolo(fascicolo))
    tipi = {(m["tipo"], m["prima"], m["dopo"]) for m in modifiche}
    assert ("stile", "somma", "sorte capitale") in tipi
    assert any(t == "completamento" for t, _, _ in tipi)
    assert ("dati", "9.960,50", "9.960,00") in tipi


def test_un_completamento_non_nasconde_una_frase_tolta():
    tolta = ("[DA COMPLETARE: scadenza] e poi la ricorrente ha emesso le fatture n. 455/2025 "
             "e n. 489/2025 per complessivi euro 9.960,50")
    modifiche = learning.confronta(f"Le scadenze sono: {tolta}.", "Le scadenze sono: 30 giorni.")
    assert [m["tipo"] for m in modifiche] == ["riscrittura"]


def test_una_correzione_non_si_spezza_su_una_parola_in_comune():
    modifiche = learning.confronta("3. Per le predette prestazioni la ricorrente ha emesso",
                                   "3. A fronte delle prestazioni indicate la ricorrente ha emesso")
    assert [(m["tipo"], m["prima"], m["dopo"]) for m in modifiche] == [
        ("stile", "Per le predette prestazioni", "A fronte delle prestazioni indicate")]


def test_si_contano_i_dati_completati():
    modifiche = learning.confronta("Scadenze: [DA COMPLETARE: prima] e [DA COMPLETARE: seconda].",
                                   "Scadenze: 30 giorni.")
    assert learning.conta(modifiche)["completamento"] == 2


def test_una_correzione_in_due_atti_diventa_regola(db, fascicolo, config, profilo, massimario,
                                                    tmp_path):
    registro = tmp_path / "correzioni.json"
    testo, firmato = bozza_e_firmato(db, fascicolo, config, profilo, massimario, tmp_path)
    modifiche = learning.confronta(testo, firmato, draft.sensibili_del_fascicolo(fascicolo))
    learning.aggiorna_correzioni(registro, "sarti", "2026-041", modifiche)
    assert learning.regole_apprese(registro, "sarti") == []  # un atto solo: osservata
    learning.aggiorna_correzioni(registro, "sarti", "2026-052", modifiche)
    regole = learning.regole_apprese(registro, "sarti")
    assert regole == ["Scrivi «sorte capitale», non «somma» (corretto in 2 atti)."]
    assert learning.regole_apprese(registro, "dini") == []


def test_lo_stesso_atto_non_fa_una_regola(tmp_path):
    registro = tmp_path / "correzioni.json"
    modifiche = learning.confronta("la somma di euro 10, poi la somma di euro 20",
                                   "la sorte capitale di euro 10, poi la sorte capitale di euro 20")
    assert [m["tipo"] for m in modifiche] == ["stile", "stile"]
    learning.aggiorna_correzioni(registro, "sarti", "2026-041", modifiche)
    learning.aggiorna_correzioni(registro, "sarti", "2026-041", modifiche)  # approvato di nuovo
    assert learning.regole_apprese(registro, "sarti") == []


def test_una_riscrittura_non_diventa_regola(tmp_path):
    registro = tmp_path / "correzioni.json"
    modifiche = learning.confronta(
        "Il servizio è stato prestato regolarmente per tutto l'anno.",
        "Ogni mese la ricorrente ha inviato i rapporti di intervento, sottoscritti dal cliente "
        "senza alcuna contestazione.")
    assert [m["tipo"] for m in modifiche] == ["riscrittura"]
    for numero in ("2026-041", "2026-052"):
        learning.aggiorna_correzioni(registro, "sarti", numero, modifiche)
    assert learning.regole_apprese(registro, "sarti") == []


def test_nelle_regole_i_numeri_diventano_segnaposto(tmp_path):
    registro = tmp_path / "correzioni.json"
    for numero, importo in (("2026-041", "80,00"), ("2026-052", "120,00")):
        modifiche = learning.confronta(
            f"oltre euro {importo} per i costi di recupero",
            f"oltre euro {importo} (euro 40,00 per ciascuna fattura) per i costi di recupero")
        learning.aggiorna_correzioni(registro, "sarti", numero, modifiche)
    assert learning.regole_apprese(registro, "sarti") == [
        "Aggiungi «(euro [NUMERO] per ciascuna fattura)» dopo «oltre euro [NUMERO]» "
        "(aggiunto in 2 atti)."]
    assert "40,00" not in registro.read_text("utf-8")


def test_le_regole_non_contengono_dati_dei_clienti(db, fascicolo, config, profilo, massimario,
                                                   tmp_path):
    registro = tmp_path / "correzioni.json"
    testo, firmato = bozza_e_firmato(db, fascicolo, config, profilo, massimario, tmp_path)
    firmato = firmato.replace("Hotel Belvedere Sestola S.r.l. di pagare",
                              "Hotel Belvedere Sestola S.r.l., in persona del legale "
                              "rappresentante pro tempore, di pagare")
    modifiche = learning.confronta(testo, firmato, draft.sensibili_del_fascicolo(fascicolo))
    learning.aggiorna_correzioni(registro, "sarti", "2026-041", modifiche)
    contenuto = registro.read_text("utf-8")
    for dato in ("Belvedere", "Taddei", "Sestola", "03555440361", "Rotative", "9.960"):
        assert dato not in contenuto
    assert "in persona del legale rappresentante pro tempore" in contenuto


def test_l_avvocato_puo_respingere_una_regola(tmp_path):
    registro = tmp_path / "correzioni.json"
    modifiche = learning.confronta("la somma di euro", "la sorte capitale di euro")
    for numero in ("2026-041", "2026-052"):
        learning.aggiorna_correzioni(registro, "sarti", numero, modifiche)
    assert len(learning.regole_apprese(registro, "sarti")) == 1
    learning.respingi(registro, "sarti", 1)
    learning.aggiorna_correzioni(registro, "sarti", "2026-060", modifiche)
    assert learning.regole_apprese(registro, "sarti") == []  # resta respinta
    with pytest.raises(ValueError, match="non c'è la correzione numero 5"):
        learning.respingi(registro, "sarti", 5)


def test_un_aggiunta_all_inizio_dell_atto(tmp_path):
    registro = tmp_path / "correzioni.json"
    modifiche = learning.confronta("Ricorso per decreto ingiuntivo", "URGENTE Ricorso per decreto ingiuntivo")
    for numero in ("2026-041", "2026-052"):
        learning.aggiorna_correzioni(registro, "sarti", numero, modifiche)
    assert learning.regole_apprese(registro, "sarti") == [
        "Aggiungi «URGENTE» all'inizio dell'atto (aggiunto in 2 atti)."]


def test_la_regola_arriva_al_modello_e_si_controlla_dopo(db, fascicolo, config, profilo,
                                                         massimario, tmp_path):
    voce = {"prima": "somma", "dopo": "sorte capitale", "volte": 2,
            "fascicoli": ["2026-041", "2026-052"], "contesti": ["dalla notifica, la"]}
    bozza = draft.prepara(db, fascicolo, config, profilo, massimario, ModelloFinto(),
                          tmp_path, apprese=[voce])
    assert ("REGOLE APPRESE DALLE CORREZIONI DELL'AVVOCATO: "
            "Scrivi «sorte capitale», non «somma» (corretto in 2 atti).") in bozza.inviato
    # Il modello finto non segue le regole apprese: il controllo lo dice all'avvocato.
    assert ("REGOLA APPRESA NON SEGUITA: la bozza scrive ancora «somma», che l'avvocato ha "
            "corretto in «sorte capitale» in 2 atti.") in bozza.avvisi


def test_una_regola_seguita_non_da_avvisi():
    voci = [{"prima": "euro [NUMERO] per i costi", "dopo": "", "fascicoli": ["a", "b"]}]
    assert learning.non_rispettate("la sorte capitale di euro 9.960,50", voci) == []
    assert len(learning.non_rispettate("oltre euro 80,00 per i costi di recupero", voci)) == 1


def test_un_atto_escluso_non_fa_da_esempio(db, fascicolo, config, profilo, massimario, tmp_path):
    curatela_file = tmp_path / "curatela.json"
    fascicolo["stile"] = "dini"
    senza = draft.prepara(db, fascicolo, config, profilo, massimario, ModelloFinto(), tmp_path)
    assert "06" in senza.esempi  # senza curatela, l'atto mediocre fa da esempio
    curatela = learning.segna_esempio(curatela_file, "06", False, "interessi generici")
    bozza = draft.prepara(db, fascicolo, config, profilo, massimario, ModelloFinto(), tmp_path,
                          curatela=curatela)
    assert bozza.esempi == ["08", "04"]
    assert json.loads(curatela_file.read_text())["esempi"]["06"]["esempio"] is False


def test_l_atto_firmato_entra_nell_archivio(config, fascicolo, profilo, massimario, tmp_path):
    db = archive.apri(tmp_path / "prova.db")
    archive.importa(RADICE / "archivio/pdf", db, config)
    testo, firmato = bozza_e_firmato(db, fascicolo, config, profilo, massimario, tmp_path)
    archive.importa_testo(db, "2026-041", "approvati/2026-041", firmato, autore="sarti",
                          tipo="ricorso decreto ingiuntivo", giudice="Tribunale di Modena",
                          valore=9960.0, data="2026-10-20")
    risultati = search.cerca(db, "stampa di cataloghi per un albergo", autore="sarti")
    assert risultati[0].atto_id == "2026-041"
    ruoli = [r["ruolo"] for r in db.execute(
        "select ruolo from sezioni where atto_id = '2026-041' order by ordine")]
    assert "fatti" in ruoli and "conclusioni" in ruoli


def test_i_dati_dell_atto_firmato_restano_nascosti(config, fascicolo, profilo, massimario,
                                                   tmp_path):
    """Un nome senza titolo né ruolo sfugge alle regole: lo nasconde la scheda dell'atto."""
    db = archive.apri(tmp_path / "prova.db")
    archive.importa(RADICE / "archivio/pdf", db, config)
    firmato = ("TRIBUNALE DI MODENA\n\nRicorso per decreto ingiuntivo\n\n"
               "Officine Grafiche Taddei S.r.l., rappresentata da Giorgio Taddei, ha stampato "
               "i cataloghi della stagione invernale per un albergo.\n\n"
               "Modena, 20 ottobre 2026\n\nAvv. Elena Sarti")
    altro_cliente = dict(
        fascicolo, id="2026-052", rapporto="la stampa di cataloghi per un albergo",
        ricorrente={"nome": "Cartotecnica Ferri S.r.l.", "piva": "01234567897",
                    "sede": "Via dei Mille 5, Carpi", "rappresentante": "Anna Ferri"},
        intimata={"nome": "Albergo Cimone S.r.l.", "piva": "09876543217",
                  "sede": "Via Roma 1, Fanano"})

    def richiesta(riservati):
        archive.importa_testo(db, "2026-041", "approvati/2026-041", firmato, autore="sarti",
                              tipo="ricorso decreto ingiuntivo", giudice="Tribunale di Modena",
                              valore=9960.5, data="2026-10-20", riservati=riservati)
        bozza = draft.prepara(db, altro_cliente, config, profilo, massimario, ModelloFinto(),
                              tmp_path)
        assert "2026-041" in bozza.esempi
        return bozza.inviato

    assert "Giorgio" in richiesta(None)  # senza la scheda, il nome partirebbe
    assert "Giorgio" not in richiesta(draft.sensibili_del_fascicolo(fascicolo))


def test_almeno_un_esempio_e_scritto_senza_minuta(config, fascicolo, profilo, massimario,
                                                  tmp_path):
    """Se gli esempi fossero solo bozze approvate, lo stile scivolerebbe verso il modello."""
    db = archive.apri(tmp_path / "prova.db")
    archive.importa(RADICE / "archivio/pdf", db, config)
    for numero in ("2026-041", "2026-052"):
        testo, firmato = bozza_e_firmato(db, dict(fascicolo, id=numero), config, profilo,
                                         massimario, tmp_path)
        archive.importa_testo(db, numero, f"approvati/{numero}", firmato, autore="sarti",
                              tipo="ricorso decreto ingiuntivo", giudice="Tribunale di Modena",
                              valore=9960.5, data="2026-10-20")
    assert archive.approvati(db) == {"2026-041", "2026-052"}
    esempi = [r.atto_id for r in draft.scegli_esempi(db, "sarti", fascicolo["rapporto"], {})]
    assert esempi[0] in {"2026-041", "2026-052"}
    assert esempi[1] not in {"2026-041", "2026-052"}


def test_gli_atti_firmati_sopravvivono_al_database(fascicolo, tmp_path):
    cartella = tmp_path / "approvati"
    archive.salva_approvato(cartella, "TRIBUNALE DI MODENA\n\nRicorso.\n\nAvv. Elena Sarti", {
        "atto_id": "2026-041", "autore": "sarti", "tipo": "ricorso decreto ingiuntivo",
        "giudice": "Tribunale di Modena", "valore": 9960.5, "data": "2026-10-20",
        "riservati": draft.sensibili_del_fascicolo(fascicolo)})
    nuovo = archive.apri(tmp_path / "ricostruito.db")
    assert [a.id for a in archive.importa_approvati(cartella, nuovo)] == ["2026-041"]
    assert archive.riservati(nuovo, "2026-041")["Giorgio Taddei"] == "PERSONA"
    assert archive.importa_approvati(tmp_path / "non-esiste", nuovo) == []


def test_il_comando_approva(db, fascicolo, config, profilo, massimario, tmp_path, monkeypatch,
                            capsys):
    (tmp_path / "config").mkdir()
    shutil.copy(RADICE / "config/studio.json", tmp_path / "config/studio.json")
    monkeypatch.setattr(comandi, "RADICE", tmp_path)
    for numero in ("2026-041", "2026-052"):
        dati = dict(fascicolo, id=numero)
        bozza = draft.prepara(db, dati, config, profilo, massimario, ModelloFinto(),
                              tmp_path / "registro")
        markdown = tmp_path / f"{numero}-20261005-120000.md"
        markdown.write_text(draft.in_markdown(bozza, dati), "utf-8")
        firmato = tmp_path / f"{numero}-firmato.txt"
        firmato.write_text(bozza.testo.replace("la somma di euro", "la sorte capitale di euro")
                           .replace("[DA COMPLETARE: luogo e data]", "Modena, 20 ottobre 2026,"),
                           "utf-8")
        scheda = tmp_path / f"{numero}.json"
        scheda.write_text(json.dumps(dati), "utf-8")
        assert comandi.main(["approva", str(markdown), "--finale", str(firmato),
                             "--avvocato", "sarti", "--fascicolo", str(scheda)]) == 0
    comandi.main(["correzioni", "--avvocato", "sarti"])
    uscita = capsys.readouterr().out
    assert ("approvata da sarti: 1 completamento, 0 modifiche di dati, 1 correzione di stile, "
            "0 riscritture") in uscita
    assert "1. [regola] «somma» → «sorte capitale»  (in 2 atti, 2 volte)" in uscita
    assert (tmp_path / "archivio/approvati/2026-052.json").exists()
    eventi = [json.loads(r) for r in (tmp_path / "registro/uso-ai.jsonl").read_text().splitlines()]
    approvazioni = [e for e in eventi if e.get("evento") == "approvazione"]
    assert [e["approvata_da"] for e in approvazioni] == ["sarti", "sarti"]
    firmato_052 = learning.testo_della_bozza(firmato.read_text("utf-8"))
    assert approvazioni[1]["firmato_sha256"] == hashlib.sha256(firmato_052.encode()).hexdigest()
    # Una bozza con il fascicolo sbagliato non si approva.
    with pytest.raises(SystemExit):
        comandi.main(["approva", str(markdown), "--finale", str(firmato), "--avvocato", "sarti",
                      "--fascicolo", str(tmp_path / "2026-041.json")])
    assert "la bozza è del fascicolo 2026-052, non del 2026-041" in capsys.readouterr().err


def test_la_bozza_si_ripulisce_prima_del_confronto():
    markdown = ("> **BOZZA** · fascicolo 1\n\nTesto del paragrafo.\n\n"
                "<sub>provenienza: fascicolo</sub>\n\n---\n\n## Note per l'avvocato\n- nessuna")
    assert learning.testo_della_bozza(markdown) == "Testo del paragrafo."


def test_i_numeri_di_pagina_non_sono_correzioni():
    assert learning.testo_firmato(["Primo paragrafo.", "Pagina 1 di 2", "2", "Secondo."]) == (
        "Primo paragrafo.\n\nSecondo.")
