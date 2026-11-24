-- Schemat SQLite: definicje obiektów, bez rekordów.
-- Wewnętrzne obiekty sqlite_* są pomijane.

CREATE TABLE autorzy (autor_id INTEGER PRIMARY KEY AUTOINCREMENT, autor_nazwa TEXT NOT NULL, aliases TEXT NOT NULL, autor_url TEXT, autor_lata TEXT);

CREATE TABLE cenzura (cenzura_id INTEGER PRIMARY KEY AUTOINCREMENT, cenzura_numer TEXT NOT NULL, year_from TEXT (4) NOT NULL, year_to TEXT (4));

CREATE TABLE miasta (miasto_id INTEGER PRIMARY KEY AUTOINCREMENT, miasto_nazwa TEXT NOT NULL, aliases TEXT, "default" INTEGER);

CREATE TABLE wydanie (wydanie_id INTEGER PRIMARY KEY AUTOINCREMENT, wzor_id INTEGER NOT NULL, wydanie_numer TEXT NOT NULL, wydanie_rok TEXT (4) NOT NULL, wydanie_tag TEXT, cenzura_id INTEGER, wydanie_cenzura TEXT, wydanie_naklad INTEGER, wydanie_zamowienie TEXT, awers_id INTEGER UNIQUE, rewers_id INTEGER UNIQUE);

CREATE TABLE wydawcy (wydawca_id INTEGER PRIMARY KEY, wydawca_nazwa TEXT NOT NULL UNIQUE);

CREATE TABLE wzory (wzor_id INTEGER PRIMARY KEY AUTOINCREMENT, wydawca_id INTEGER NOT NULL, wzor_numer INTEGER NOT NULL, autor_id INTEGER, miasto_id INTEGER, wzor_opis TEXT);
