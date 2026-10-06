-- [libro:sql-leggere]
SELECT * FROM persone;
SELECT codice, materia, minuti_studio FROM fascicoli;
SELECT codice, minuti_studio FROM fascicoli WHERE documentata = 0;
SELECT codice, minuti_studio FROM fascicoli ORDER BY minuti_studio DESC;
-- [/libro:sql-leggere]
