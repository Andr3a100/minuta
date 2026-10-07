# La lingua della lettura ottica

`ita.traineddata` è il modello per l'italiano di Tesseract, il motore di
lettura ottica che PyMuPDF contiene già: con questo file Minuta legge le
scansioni senza programmi da installare (lezione 16). La lettura ottica gira
sul computer dello studio, perché un'immagine non si può pseudonimizzare: i
nomi sono dentro i pixel.

- origine: repository `tesseract-ocr/tessdata_fast`, versione 4.1.0,
  https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/ita.traineddata
- scaricato il 7 ottobre 2026; 2.701.314 byte
- SHA-256: `b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827`
- licenza: Apache 2.0, nel file `LICENSE` accanto, copiato dallo stesso
  repository.

I modelli «fast» sono i più piccoli e i più veloci. La prova
`tests/test_documenti.py` controlla l'impronta del file e la lettura di una
scansione.
