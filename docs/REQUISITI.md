# Minuta: requisiti

Minuta è l'assistente di **un solo studio legale**: il praticante che ha
letto tutto. Legge il fascicolo, segna le scadenze, prepara le verifiche,
risponde alle domande citando documento e pagina, e scrive bozze nello stile
dello studio. Nel caso del libro lo studio è Studio Meridiana, società tra
avvocati: Elena Sarti e Marco Dini (civile), Paola Righi (tributario),
Stefano Valli (penale), la praticante Irene, Rosa in segreteria.

Ogni testo che Minuta produce è una bozza. Il lavoro intellettuale resta
dell'avvocato: Minuta svolge attività strumentali e di supporto, come chiede
l'art. 13 della legge 132/2025.

## Fuori perimetro

Minuta non deposita atti e non notifica; non manda niente al cliente né a
terzi; non conclude sul merito, cioè non scrive mai «l'atto è nullo» o «il
debito non è dovuto»; non firma. Restano fuori anche più studi nello stesso
archivio, la contabilità e la fatturazione dello studio, l'addestramento di
modelli sui documenti dei clienti. Ognuna di queste richieste avrà
un'analisi propria: non è «soltanto un pulsante».

## Requisiti

La colonna «Dove si prova» indica la lezione che costruisce il requisito e,
quando c'è già, la prova del pilota che lo copre. Quando una lezione lo
costruisce, accanto compare il file della prova.

| N. | Requisito | Dove si prova |
|---|---|---|
| REQ-01 | Si accede con nome utente e passphrase di almeno 15 caratteri. Gli account si creano con un comando di amministrazione: non esiste la registrazione pubblica. | lezione 15 |
| REQ-02 | Tre ruoli. **Avvocato**: decide, e solo lui approva una bozza. **Praticante**: prepara e controlla schede, scadenze, verifiche e bozze, ma non approva. **Segreteria**: apre i fascicoli, carica i documenti, tiene lo scadenziario; non fa richieste al modello. | lezione 15 |
| REQ-03 | Ogni fascicolo ha le sue persone. Chi non vi è assegnato non lo vede, non lo apre e non ne cerca i documenti, nemmeno scrivendo l'indirizzo a mano: la risposta è 404. | lezioni 15 e 32 |
| REQ-04 | Ogni richiesta al modello lascia una voce nel registro dell'uso dell'AI: quando, chi, modello, fascicolo o «nessuno», categorie dei dati usciti, scopo, impronta del testo inviato, controllo, approvazione. Mai il testo inviato. La voce si salva nella stessa transazione dell'azione che la produce. | `test_bozza.py` (pilota, in parte); lezione 15 |
| REQ-05 | Nessun testo entra in un atto o arriva a un cliente senza l'approvazione di un avvocato, registrata con il nome e la data. Un atto in cui restano parti della bozza non si registra come approvato senza una forzatura, che il registro conserva. | `test_word.py` (pilota); lezione 24 |
| REQ-06 | Minuta legge PDF con testo, scansioni con la lettura ottica, file Word, buste `.p7m` e fatture FatturaPA. Il testo ottenuto con la lettura ottica è segnato come trascrizione da controllare. | `test_documenti.py`, `test_fatture.py`; lezione 16 |
| REQ-07 | Prima di qualunque invio, ogni PDF passa dal controllo del testo nascosto: bianco, minuscolo, fuori dalla pagina. Ciò che trova si mostra all'avvocato. | `test_nascosti.py`, `test_documenti.py`; lezione 16 |
| REQ-08 | Di una busta `.p7m` Minuta dice due cose separate: se il documento è integro e se il certificato di chi ha firmato è verificato. Non presenta mai la prima come la seconda. | `test_documenti.py`; lezione 16 |
| REQ-09 | Prima di ogni invio al modello, i nomi dell'elenco delle persone del fascicolo e gli identificativi (codici fiscali, partite IVA, IBAN, PEC, indirizzi) diventano segnaposto. Se nel testo da inviare resta qualcosa di riconoscibile, l'invio si blocca. | `test_pseudonimi.py`, `test_bozza.py` (pilota); lezione 17 |
| REQ-10 | Le istruzioni di sistema dicono al modello che i documenti sono materiale da leggere, mai ordini da eseguire. | lezione 18 |
| REQ-11 | La scheda dell'atto in arrivo cita per ogni dato il documento e la pagina. Minuta controlla che ogni data e ogni importo compaiano davvero in quella pagina; ciò che non si ritrova è segnalato. | lezione 18 |
| REQ-12 | Le scadenze le calcola Minuta, con regole scritte in un file leggibile: durata, decorrenza, sospensioni, giorni festivi, ciascuna con la norma letta sulla fonte ufficiale e la data di lettura. Il modello cerca solo la data di partenza, che deve comparire nel documento. Ogni scadenza resta «da verificare» finché un avvocato non la conferma. | lezione 19 |
| REQ-13 | Per ogni tipo di atto, un elenco di domande in un file leggibile. Minuta le riempie con i fatti e le pagine del fascicolo e con lo stato: aperta, verificata dall'avvocato, non pertinente. Non conclude sul merito. | lezione 20 |
| REQ-14 | Alle domande sul fascicolo Minuta risponde solo dai suoi documenti e dagli atti dell'archivio, citando documento e pagina. Se la risposta non c'è, dice che nel fascicolo non c'è. | lezione 21 |
| REQ-15 | L'archivio dello studio si carica e si cerca per tipo di atto, autore e periodo. I nomi dei clienti di un atto d'archivio non entrano nella bozza di un altro: restano segnaposto, e una bozza che li usa riceve un avviso. | `test_ricerca.py`, `test_bozza.py` (pilota); lezione 22 |
| REQ-16 | Lo stile di ogni avvocato sta in un profilo leggibile, che l'avvocato corregge. Ogni formula dice da quali atti viene; il profilo non contiene dati personali. | `test_profilo.py` (pilota); lezione 23 |
| REQ-17 | La bozza dice da dove viene ogni paragrafo, evidenzia le parti da completare ed esce in Word, impaginata secondo l'art. 6 del DM 110/2023. | `test_word.py` (pilota); lezione 24 |
| REQ-18 | Il promemoria per il cliente dice in parole semplici che cosa è arrivato, che cosa rischia, che cosa si può fare ed entro quando. | lezione 24 |
| REQ-19 | Ogni norma citata nella bozza si confronta con il massimario dello studio, fatto di testi letti sulla fonte ufficiale con la data di lettura. Una norma assente o non pertinente al caso è segnalata. | `test_citazioni.py`, `test_bozza.py` (pilota); lezione 25 |
| REQ-20 | Una correzione di stile diventa una regola solo dopo due atti diversi. Le regole vanno nella richiesta al modello e si controllano sulla bozza. Fra gli esempi resta sempre almeno un atto scritto senza Minuta. | `test_apprendimento.py` (pilota); lezione 26 |
| REQ-21 | Una suite di casi con risposta nota misura schede, scadenze, verifiche e citazioni. Ogni modifica di Minuta la deve superare prima di entrare in uso. | lezione 27 |
| REQ-22 | La chiave del fornitore sta in un file fuori dal repository. Non compare nel registro, nelle pagine, nei messaggi d'errore. | lezione 15 |
| REQ-23 | Fornitore e modello si scelgono nella configurazione. Ogni chiamata registra il modello, i token e il costo. | lezioni 15 e 31 |
