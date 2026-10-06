-- [libro:sql-errore]
UPDATE fascicoli SET documentata = 1;
SELECT changes();
SELECT codice, documentata FROM fascicoli;
-- [/libro:sql-errore]
