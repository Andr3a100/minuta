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
| Prepara la bozza: provenienza, citazioni, pertinenza, segnaposto di altri clienti | `draft.py` | provato con il modello finto |
| Parla con i modelli in cloud (Anthropic; servizi compatibili con OpenAI) | `model.py` | PROCEDURA: non ancora provato con una chiave vera |
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
.venv/bin/python -m pytest -q
```

Con un modello vero:
- `MINUTA_MODELLO=anthropic` e la chiave in `ANTHROPIC_API_KEY`;
- oppure `MINUTA_MODELLO=openai`, con `MINUTA_BASE_URL`, `MINUTA_MODELLO_NOME` e la chiave in `MINUTA_API_KEY`.

Le chiavi non vanno mai nei file del repository.

## L'archivio di prova

Dieci atti inventati di *Studio Meridiana* (2019-2026): nove ricorsi per
decreto ingiuntivo e una diffida, di due avvocati con stili diversi. Ci sono
di proposito un atto mediocre (06) e due ricorsi con richiesta di
provvisoria esecuzione, su presupposti diversi (05, 10).

Persone, società, codici e indirizzi sono inventati, e le PEC usano il
dominio riservato `.example`. Le norme citate sono reali. **Gli atti vanno
rivisti da un avvocato** prima di entrare nel libro.

## Regole

- L'archivio resta in locale; al modello arriva solo testo pseudonimizzato.
- I segnaposto degli esempi (`[E1_...]`) non si ricompongono mai nella bozza di un altro cliente.
- Una citazione che non è nel massimario resta «da verificare».
- Ogni chiamata è registrata in `registro/uso-ai.jsonl`: modello, impronta del testo inviato, token, esempi usati, esito del controllo fughe, approvazione.
- Licenza: da decidere.
