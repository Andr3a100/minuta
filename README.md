# Minuta

L'assistente supervisionato di uno studio legale. Legge l'archivio dello
studio, ritrova i precedenti, prepara bozze nello stile dello studio. Ogni
testo che produce è una **bozza**: l'avvocato la rivede, la corregge e la
firma.

È il laboratorio del libro *Minuta*. Questo è il **pilota tecnico** del 5
ottobre 2026, su un solo tipo di atto: il ricorso per decreto ingiuntivo.

## Che cosa fa

| Passo | Modulo | Stato |
|---|---|---|
| Legge i PDF dell'archivio: legature, a capo, sezioni, metadati | `archive.py` | provato |
| Pseudonimizza in modo reversibile: nomi, società, codici fiscali, partite IVA, indirizzi, PEC, IBAN | `pseudonym.py` | provato |
| Blocca l'invio se qualcosa di riconoscibile sta per partire | `leaks.py` | provato |
| Ritrova i precedenti, filtrando per tipo, autore e periodo | `search.py` | provato |
| Ricava il profilo dello studio: stile di ogni avvocato, formule con i loro atti | `profile.py` | provato |
| Costruisce il massimario e verifica le norme su Normattiva | `citations.py` | provato |
| Prepara la bozza: provenienza, citazioni, pertinenza, completezza, segnaposto di altri clienti, regole apprese | `draft.py` | provato con il modello finto e con OpenAI |
| Impara dall'avvocato senza addestrare un modello: atti modello, atti firmati che diventano esempi, correzioni che diventano regole | `learning.py` | provato con il modello finto e con OpenAI, su correzioni simulate |
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
.venv/bin/python -m minuta bozza tests/fascicolo-prova.json --modello finto
.venv/bin/python -m minuta esempio 06 --no --motivo "interessi generici"
.venv/bin/python -m minuta approva bozze/2026-041-....md --finale firmato.pdf \
    --avvocato sarti --fascicolo tests/fascicolo-prova.json
.venv/bin/python -m minuta correzioni --avvocato sarti
.venv/bin/python -m pytest -q
```

Con un modello vero:
- `MINUTA_MODELLO=openai` e `MINUTA_MODELLO_NOME` (per esempio `gpt-6.1-sol`), con la chiave in `OPENAI_API_KEY` nel file `.env`; `MINUTA_BASE_URL` serve solo per un servizio compatibile diverso da OpenAI;
- oppure `MINUTA_MODELLO=anthropic` e la chiave in `ANTHROPIC_API_KEY`.

Il file `.env` resta sul computer dello studio: git lo ignora e Minuta non
stampa mai la chiave. Le chiavi non vanno mai nei file del repository.

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
