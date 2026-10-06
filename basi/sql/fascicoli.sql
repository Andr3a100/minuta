-- [libro:fascicoli-sql]
-- I fascicoli ricostruiti a mano nella lezione 2, in un database.
CREATE TABLE persone (
    id    INTEGER PRIMARY KEY,
    nome  TEXT NOT NULL UNIQUE,
    ruolo TEXT NOT NULL
);

CREATE TABLE fascicoli (
    codice         TEXT PRIMARY KEY,
    materia        TEXT NOT NULL
                   CHECK (materia IN ('civile', 'tributario', 'penale')),
    notificato_il  TEXT NOT NULL,         -- data nel formato aaaa-mm-gg
    studiato_da    INTEGER REFERENCES persone (id),
    giorni_prima   INTEGER NOT NULL CHECK (giorni_prima >= 0),
    minuti_studio  INTEGER NOT NULL CHECK (minuti_studio >= 0),
    minuti_stesura INTEGER NOT NULL CHECK (minuti_stesura >= 0),
    errori         INTEGER NOT NULL DEFAULT 0,
    documentata    INTEGER NOT NULL DEFAULT 0 CHECK (documentata IN (0, 1))
);

INSERT INTO persone (id, nome, ruolo) VALUES
    (1, 'Elena Sarti', 'avvocato'),
    (2, 'Paola Righi', 'avvocato'),
    (3, 'Stefano Valli', 'avvocato'),
    (4, 'Irene', 'praticante');

INSERT INTO fascicoli VALUES
    ('F-01', 'civile',     '2026-09-01', 4,     3,  95, 120, 1, 0),
    ('F-02', 'tributario', '2026-09-02', 2,    11, 140,  90, 0, 1),
    ('F-03', 'penale',     '2026-09-03', 3,     2, 210, 150, 2, 0),
    ('F-04', 'civile',     '2026-09-07', NULL,  7,  60,  80, 0, 1),
    ('F-05', 'tributario', '2026-09-08', 2,     5, 125, 110, 1, 0);
-- [/libro:fascicoli-sql]
