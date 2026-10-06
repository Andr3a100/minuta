-- [libro:sql-transazione]
BEGIN;
UPDATE fascicoli SET documentata = 1;
SELECT changes();
ROLLBACK;
SELECT codice, documentata FROM fascicoli;
-- [/libro:sql-transazione]
