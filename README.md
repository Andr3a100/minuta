# Minuta

L'assistente supervisionato di uno studio legale. Legge l'archivio dello
studio, ritrova i precedenti, prepara bozze nello stile dello studio. Ogni
testo che produce è una **bozza**: l'avvocato la rivede, la corregge e la
firma.

È il laboratorio del libro *Minuta*. Questo è il **pilota tecnico** del 5
ottobre 2026, su un solo tipo di atto: il ricorso per decreto ingiuntivo.

## Le versioni

Ogni lezione della Parte III del libro lavora su una versione di Minuta,
segnata nel repository con un'etichetta: `git switch --detach v0.1` porta la
cartella alla versione della lezione 15. I file che il programma crea sul
tuo computer (`.env`, il database, l'ambiente virtuale) restano dove sono.

| Versione | Lezione | Che cosa aggiunge |
|---|---|---|
| 0.1 | 15 | l'applicazione: accessi, ruoli, fascicoli, i due registri |
| 0.2 | 16 | i documenti del fascicolo: PDF, lettura ottica, Word, fatture elettroniche, buste firmate, testo nascosto |

## Che cosa fa

| Passo | Modulo | Stato |
|---|---|---|
| Legge i PDF dell'archivio: legature, a capo, sezioni, metadati | `archive.py` | provato |
| Prepara il fascicolo dalle fatture elettroniche (FatturaPA, anche firmate .p7m): parti, importi, scadenze, note di credito, documenti di trasporto, ordini | `fatture.py` | provato su fatture inventate, valide secondo lo schema ufficiale 1.2.3 |
| Pseudonimizza in modo reversibile: nomi, società, codici fiscali, partite IVA, indirizzi, PEC, IBAN | `pseudonym.py` | provato |
| Blocca l'invio se qualcosa di riconoscibile sta per partire | `leaks.py` | provato |
| Ritrova i precedenti, filtrando per tipo, autore e periodo | `search.py` | provato |
| Ricava il profilo dello studio: stile di ogni avvocato, formule con i loro atti | `profile.py` | provato |
| Costruisce il massimario e verifica le norme su Normattiva | `citations.py` | provato |
| Prepara la bozza: provenienza, citazioni, pertinenza, completezza, segnaposto di altri clienti, regole apprese | `draft.py` | provato con il modello finto e con OpenAI |
| Impara dall'avvocato senza addestrare un modello: atti modello, atti firmati che diventano esempi, correzioni che diventano regole | `learning.py` | provato con il modello finto e con OpenAI, su correzioni simulate |
| Consegna la bozza in Word (.docx) e rilegge l'atto firmato, revisioni comprese | `word.py` | provato su bozze vere di OpenAI e su correzioni simulate; aperto in Word da Andrea il 6 ottobre 2026 |
| Parla con i modelli in cloud: OpenAI (provato il 5 ottobre 2026 con gpt-6.1-sol e gpt-6-astra) e Anthropic (non ancora provato) | `model.py` | OpenAI provato; Anthropic PROCEDURA |
| Esporta gli esempi per l'addestramento (livello 2), pseudonimizzati | `__main__.py` | provato |

## Come si usa

```
python3.13 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python strumenti/genera_pdf.py        # PDF dell'archivio di prova
.venv/bin/python -m minuta importa
.venv/bin/python -m minuta profilo
.venv/bin/python -m minuta cerca "riconoscimento di debito" --autore sarti
.venv/bin/python strumenti/genera_fatture.py      # fatture elettroniche di prova
.venv/bin/python -m minuta fascicolo archivio/fatture/*.xml --numero 2026-041 --avvocato sarti
.venv/bin/python -m minuta bozza tests/fascicolo-prova.json --modello finto   # .md e .docx
.venv/bin/python -m minuta word bozze/2026-041-....md     # una bozza già fatta, in Word
.venv/bin/python -m minuta esempio 06 --no --motivo "interessi generici"
.venv/bin/python -m minuta approva bozze/2026-041-....docx --finale firmato.docx \
    --avvocato sarti --fascicolo tests/fascicolo-prova.json
.venv/bin/python -m minuta correzioni --avvocato sarti
.venv/bin/python -m pytest -q
```

Con un modello vero:
- `MINUTA_MODELLO=openai` e `MINUTA_MODELLO_NOME` (per esempio `gpt-6.1-sol`), con la chiave in `OPENAI_API_KEY` nel file `.env`; `MINUTA_BASE_URL` serve solo per un servizio compatibile diverso da OpenAI;
- oppure `MINUTA_MODELLO=anthropic` e la chiave in `ANTHROPIC_API_KEY`.

Il file `.env` resta sul computer dello studio: git lo ignora e Minuta non
stampa mai la chiave. Le chiavi non vanno mai nei file del repository.

## Il fascicolo dalle fatture

Un ricorso per decreto ingiuntivo nasce quasi sempre da fatture non pagate, e
fra imprese le fatture sono file XML nel formato FatturaPA. `minuta fascicolo`
le legge, anche firmate (`.xml.p7m`), e scrive `fascicoli/<numero>.json`
(escluso da git):
- le parti, con partita IVA o codice fiscale e sede;
- le fatture, con importi e scadenze, e le note di credito, che si tolgono dal credito;
- i documenti di trasporto e gli ordini citati nelle fatture;
- una proposta di «rapporto» fra le parti, presa dalle causali.

Ciò che le fatture non dicono resta «da completare»: giudice, diffida, legale
rappresentante, altri documenti. L'avvocato rilegge il fascicolo prima della
bozza. Le avvertenze dicono che cosa guardare:
- fatture non ancora scadute o senza scadenza;
- importi da pagare diversi dal totale;
- note di credito e documenti che non entrano nel credito;
- un debitore senza partita IVA, che potrebbe essere un consumatore.

Formato: specifiche tecniche FatturaPA versione 1.4, in vigore dal 1° aprile
2025, schema 1.2.3. Lo schema ufficiale è in `fonti/fatturapa/`; le fatture di
prova in `archivio/fatture/` sono inventate e si convalidano su quello schema.
Dei file firmati Minuta estrae il contenuto con openssl: controlla che il
contenuto corrisponda alla firma, ma non verifica i certificati di chi ha
firmato.

## In Word

Ogni bozza esce in due file con lo stesso nome: il `.md`, che resta com'è e
serve per il confronto, e il `.docx`, che l'avvocato apre e corregge. Nel
`.docx` trova:
- in cima, un riquadro grigio con le note di Minuta: modello, esempi usati, dati da completare, stato delle citazioni;
- a margine, un commento per paragrafo con la provenienza (fascicolo, profilo, esempio, modello);
- evidenziati in giallo, i `[DA COMPLETARE]`.

Riquadro e commenti sono appunti di lavoro: prima del deposito si tolgono.
Per la provenienza Minuta usa i commenti e non le note a piè di pagina, perché
l'art. 6, comma 2, del DM 110/2023 non consente note, salvo che per la
giurisprudenza e la dottrina.

L'impaginazione di partenza segue lo stesso art. 6, comma 1 (testo vigente
letto su Normattiva il 6 ottobre 2026): caratteri di tipo corrente,
«preferibilmente» di 12 punti, interlinea 1,5, margini di 2,5 centimetri.
Minuta usa il Times New Roman. Lo studio può cambiare queste impostazioni con
la voce `impaginazione` di `config/studio.json` (`carattere`, `corpo`,
`interlinea`, `margini_cm`). Oppure può mettere la propria carta intestata in
`config/carta-intestata.docx`, o quella di un avvocato in
`config/carta-sarti.docx`: intestazione, piè di pagina e stili restano i suoi.

Per approvare, `approva` accetta il `.docx` corretto, anche se l'avvocato l'ha
salvato sopra la bozza: il confronto si fa sempre con il `.md`. Le revisioni
di Word si leggono come se fossero accettate. Se nell'atto restano il
riquadro, i commenti di Minuta, revisioni non accettate o dati da completare,
Minuta non lo registra come firmato e dice che cosa resta. Con `--comunque`
lo registra lo stesso, e il registro conserva l'elenco di ciò che restava.

## Come impara dall'avvocato

Nessun modello viene addestrato. Minuta impara in tre modi, tutti in file che
l'avvocato può leggere e correggere:

- **Gli atti modello.** `minuta esempio 06 --no --motivo "..."` toglie un atto
  dagli esempi, `--si` lo mette fra i preferiti. Le scelte stanno in
  `config/curatela.json`.
- **Gli atti firmati.** `minuta approva` mette l'atto firmato nell'archivio,
  come testo e scheda in `archivio/approvati/` (esclusi da git). Da quel
  momento fa da esempio. La scheda conserva i dati del cliente presi dal
  fascicolo: quando l'atto fa da esempio per un altro cliente, quei dati si
  nascondono anche dove nessuna regola li riconoscerebbe, e la prova delle
  fughe li cerca. Fra gli esempi resta sempre almeno un atto scritto
  dall'avvocato senza Minuta: altrimenti, bozza dopo bozza, lo stile
  scivolerebbe verso quello del modello.
- **Le correzioni.** `approva` confronta la bozza con l'atto firmato, sul testo
  pseudonimizzato, e divide le modifiche in completamenti, dati, stile e
  riscritture. Solo le correzioni di stile entrano in `config/correzioni.json`,
  con importi e date ridotti a `[NUMERO]`. Una correzione fatta in due atti
  diversi diventa una regola; una riscrittura (oltre 12 fra parole e segni di
  punteggiatura) non lo diventa mai. Le regole vanno al modello nella richiesta e poi si controllano
  sulla bozza: se il modello non le segue, la bozza lo dice nelle note per
  l'avvocato. Con `minuta correzioni --avvocato sarti --respingi N`
  l'avvocato può respingere una regola.

## L'archivio di prova

Dieci atti inventati di *Studio Meridiana* (2019-2026): nove ricorsi per
decreto ingiuntivo e una diffida, di due avvocati con stili diversi. Ci sono
di proposito un atto mediocre (06), escluso dagli esempi in
`config/curatela.json`, e due ricorsi con richiesta di provvisoria
esecuzione, su presupposti diversi (05, 10).

Persone, società, codici e indirizzi sono inventati, e le PEC usano il
dominio riservato `.example`. Le norme citate sono reali. **Gli atti vanno
rivisti da un avvocato** prima di entrare nel libro.

## Regole

- L'archivio resta in locale; al modello arriva solo testo pseudonimizzato.
- I segnaposto degli esempi (`[E1_...]`) non si ricompongono mai nella bozza di un altro cliente.
- Una citazione che non è nel massimario resta «da verificare».
- Ogni chiamata è registrata in `registro/uso-ai.jsonl`: modello, impronta del testo inviato, token, costo, esempi usati, esito del controllo fughe. Ogni approvazione vi aggiunge chi ha approvato e quante modifiche di ogni tipo ha fatto.
- Nelle correzioni apprese non entrano nomi, società, importi né date: solo lo stile.
- Licenza: da decidere.
