# Studio Meridiana · valutazione d'impatto di Minuta

Art. 35 del regolamento (UE) 2016/679. Versione del 14 ottobre 2026.
Titolare: Studio Meridiana, società tra avvocati. Firma: Elena Sarti.
Da rivedere ogni anno, e prima di ogni cambio di fornitore o di funzione.

## Perché si fa

Un singolo avvocato con i suoi clienti di regola non la deve
(considerando 91). Minuta però è un sistema di intelligenza artificiale e
tratta dati relativi a reati: per l'elenco del Garante (punto 7) la
valutazione è dovuta.

## a) I trattamenti e le finalità

Minuta legge i documenti dei fascicoli civili, tributari e penali, ne
prepara schede, scadenze, verifiche e bozze, risponde a domande sui
documenti. Lo usano quattro avvocati, una praticante e la segreteria,
sul server dello studio. Brani pseudonimizzati partono verso il modello
gpt-6.1-sol di OpenAI Ireland Ltd., responsabile del trattamento.
Interessati: clienti, controparti, persone offese, testimoni, persone
dello studio. Finalità: l'assistenza e la difesa dei clienti.

## b) Necessità e proporzionalità

Partono soltanto i passi che servono alla richiesta, senza nomi né
identificativi. Nessun dato serve ad addestrare il modello del fornitore.
L'addestramento dello studio resta sul suo server, senza nomi né fatti.
I fascicoli chiusi si conservano dieci anni, le copie trenta giorni.

## c) I rischi

R1 Un dato di un fascicolo arriva al fornitore con il nome.
R2 Una persona vede un fascicolo che non la riguarda.
R3 I dati penali e quelli sulla salute del fascicolo penale escono dalle
   persone che ci lavorano.
R4 I dati si perdono, o non si ripristinano.
R5 Un fascicolo resta oltre il tempo deciso.
R6 Un errore del modello entra in un atto: un dato inesatto su una
   persona.
R7 I dati sono trattati fuori dallo Spazio economico europeo.
R8 Il cliente non sa che lo studio usa l'intelligenza artificiale.

## d) Le misure

Le misure con un controllo si verificano con il comando
`python -m app.manage impatto`, ogni mese sul server.

M1 L'informativa al cliente: senza la consegna, niente parte. R8
M2 Segnaposto e blocco dell'invio; il registro conta le fughe. R1
M3 Nei fascicoli penali lavora soltanto chi ha la materia penale. R2 R3
M4 Copie di sicurezza ogni notte, verificate. R4
M5 La regola di conservazione è decisa, la cancellazione è completa. R5
M6 Ogni dato della bozza ha la sua fonte; l'atto lo approva un
   avvocato. R6
M7 Clausole contrattuali tipo o decisione di adeguatezza (lezione 6). R7
M8 Le copie fuori dal server viaggiano cifrate. R4
M9 Chi usa Minuta ha imparato che cosa può sbagliare (lezione 9). R6

## Il fascicolo penale

I dati relativi a reati si trattano per la difesa in giudizio (art. 10
del regolamento; art. 2-octies, comma 3, lettera e, del codice privacy).
Nel fascicolo di Riva ci sono anche dati sulla salute del lavoratore
ferito. Valgono M2 e M3, e nessuna domanda sull'archivio mescola fatti
di altri clienti.

## Conclusione

Con le misure, il rischio residuo non è elevato: non serve la
consultazione preventiva del Garante (art. 36). Se un controllo smentisce
una misura, la valutazione non vale finché la misura non torna vera.
