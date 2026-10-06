-- [libro:sql-modificare]
INSERT INTO fascicoli
    (codice, materia, notificato_il, studiato_da, giorni_prima,
     minuti_studio, minuti_stesura)
VALUES ('F-06', 'penale', '2026-09-10', 3, 4, 960, 240);
UPDATE fascicoli SET documentata = 1 WHERE codice = 'F-05';
SELECT changes();
SELECT codice, minuti_studio, documentata FROM fascicoli
WHERE codice IN ('F-05', 'F-06');
-- [/libro:sql-modificare]
