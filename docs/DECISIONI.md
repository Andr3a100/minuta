# Minuta: decisioni di architettura

Una decisione per sezione. Quando una decisione cambia, non si cancella: si
aggiunge quella nuova, che la cita.

## ADR-001 · Un'applicazione web locale, sulle fondamenta di Cantiere

- Decisione: Minuta si usa nel browser. Le pagine si compongono sul server,
  con gli accessi, i ruoli, il registro e le migrazioni di Cantiere, il
  laboratorio di *Come si arriva*.
- Alternative: un programma da terminale, come il pilota; un'interfaccia
  JavaScript separata dal server.
- Motivo: l'avvocato e la segreteria lavorano nel browser; le fondamenta di
  Cantiere sono già provate, e ogni comportamento si prova con una
  richiesta HTTP.
- Conseguenze: i comandi del pilota diventano la libreria che le pagine
  usano.

## ADR-002 · SQLite sul computer dello studio

- Decisione: un solo file di database, nella cartella di Minuta.
- Alternative: PostgreSQL fin dall'inizio.
- Motivo: si parte in un minuto, senza installare un server. Dove gira
  Minuta si decide nella lezione 30.
- Conseguenze: le migrazioni devono poter girare anche su PostgreSQL, se lo
  studio sceglierà un server.

## ADR-003 · Modello in cloud, con la pseudonimizzazione per ogni atto

- Decisione: Minuta usa il modello di un fornitore in cloud. Prima di ogni
  invio sostituisce nomi e identificativi con segnaposto, in tutte le
  materie, penale compreso.
- Alternative: un modello in locale; il cloud solo per gli atti senza dati
  delicati.
- Motivo: un solo percorso per tutti gli atti. La pseudonimizzazione è la
  regola, non un'eccezione da ricordare caso per caso.
- Conseguenze: il contratto con il fornitore (lezione 6), l'informativa al
  cliente (lezione 7) e la valutazione d'impatto (lezione 35) fanno parte
  del sistema quanto il codice.

## ADR-004 · I tipi di atto sono configurazione, non codice

- Decisione: ogni tipo di atto ha una cartella leggibile: come si
  riconosce, che cosa entra nella scheda, le regole delle scadenze con le
  loro norme, le verifiche, la struttura dell'atto di risposta.
- Alternative: un modulo di codice per ogni tipo di atto.
- Motivo: un avvocato legge e corregge un file di testo; aggiungere un tipo
  di atto non deve richiedere un programmatore.
- Conseguenze: il ricorso per decreto ingiuntivo del pilota diventa il
  primo tipo di atto; il codice legge le cartelle e le controlla.

## ADR-005 · Le scadenze le calcola Minuta, non il modello

- Decisione: il modello trova la data di partenza nel documento; il calcolo
  lo fa una funzione, con regole scritte e norme lette.
- Alternative: chiedere la scadenza al modello.
- Motivo: un calcolo si prova con casi ricavati dalle norme; la risposta di
  un modello no (lezione 13).
- Conseguenze: ogni regola porta la norma e la data di lettura, e ogni
  scadenza resta da verificare finché un avvocato non la conferma.

## ADR-006 · Imparare senza addestrare

- Decisione: Minuta impara dall'avvocato con esempi scelti, atti firmati e
  correzioni che diventano regole, senza addestrare un modello.
- Alternative: addestrare un modello sugli atti dello studio.
- Motivo: una regola si legge, si corregge e si controlla sulla bozza; ciò
  che un modello ha imparato in addestramento no. L'addestramento si valuta
  a parte, con le misure, nella lezione 28.
- Conseguenze: le regole vanno nella richiesta, e ogni bozza si controlla
  contro di esse.

## ADR-007 · Sessioni conservate sul server

- Decisione, ereditata da Cantiere: il cookie contiene un valore casuale; il
  database ne conserva solo l'impronta, con la scadenza.
- Alternative: un gettone firmato che contiene l'identità.
- Motivo: una sessione deve potersi chiudere subito, con l'uscita o con la
  disattivazione dell'account.
- Conseguenze: ogni richiesta legge la sessione dal database.
