# La prova della Parte 0

I comandi delle lezioni B2-B8 del libro, eseguiti come li scrive il lettore,
in `sessioni/unix` (zsh su macOS, bash su Linux) e in `sessioni/windows`
(Windows PowerShell 5.1). La CI (`.github/workflows/verifica.yml`) li esegue
su tre sistemi e conserva i verbali; il libro stampa gli output presi da lì.

- `LEGGIMI.md`: il file che il lettore crea nella lezione B1;
- `conti/`: le funzioni e le prove della lezione B5;
- `sql/`: il database della lezione B7;
- `documenti/`: i documenti della lezione B8, rifatti da `genera_documenti.py`.

Fuori dalla CI, `prova-basi.sh` lavora in una cartella personale temporanea.
