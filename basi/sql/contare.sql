-- [libro:sql-contare]
SELECT count(*) AS fascicoli, avg(minuti_studio) AS media_studio,
       avg(minuti_stesura) AS media_stesura
FROM fascicoli;
SELECT materia, count(*) AS quanti FROM fascicoli GROUP BY materia;
-- [/libro:sql-contare]
