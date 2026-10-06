-- [libro:sql-vincoli]
PRAGMA foreign_keys = ON;
INSERT INTO fascicoli
    (codice, materia, notificato_il, studiato_da, giorni_prima,
     minuti_studio, minuti_stesura)
VALUES ('F-07', 'civile', '2026-09-11', 9, 1, 50, 60);
INSERT INTO fascicoli
    (codice, materia, notificato_il, giorni_prima, minuti_studio,
     minuti_stesura)
VALUES ('F-08', 'lavoro', '2026-09-11', 1, 50, 60);
SELECT count(*) AS fascicoli FROM fascicoli;
-- [/libro:sql-vincoli]
