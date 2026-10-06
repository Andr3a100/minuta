-- [libro:sql-collegare]
SELECT f.codice, p.nome AS studiato_da
FROM fascicoli AS f
JOIN persone AS p ON p.id = f.studiato_da;
SELECT f.codice, p.nome AS studiato_da
FROM fascicoli AS f
LEFT JOIN persone AS p ON p.id = f.studiato_da;
-- [/libro:sql-collegare]
