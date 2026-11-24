"""Inicjalizacja osobnego katalogu danych demonstracyjnych."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from PIL import Image


def create_demo_data(root):
    root = Path(root)
    root.mkdir(parents=True)
    (root / 'instance').mkdir()
    (root / 'images').mkdir()

    with closing(sqlite3.connect(root / 'instance' / 'pocztowki.db')) as db, db:
        db.executescript("""
            CREATE TABLE miasta (
                miasto_id INTEGER PRIMARY KEY, miasto_nazwa TEXT, "default" BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE autorzy (
                autor_id INTEGER PRIMARY KEY, autor_nazwa TEXT, autor_lata TEXT, autor_url TEXT,
                alias TEXT
            );
            CREATE TABLE wydawcy (wydawca_id INTEGER PRIMARY KEY, wydawca_nazwa TEXT);
            CREATE TABLE cenzura (cenzura_id INTEGER PRIMARY KEY, cenzura_numer TEXT);
            CREATE TABLE wzory (
                wzor_id INTEGER PRIMARY KEY, wzor_opis TEXT, wzor_numer TEXT,
                miasto_id INTEGER REFERENCES miasta, autor_id INTEGER REFERENCES autorzy,
                wydawca_id INTEGER REFERENCES wydawcy
            );
            CREATE TABLE wydanie (
                wydanie_id INTEGER PRIMARY KEY, wzor_id INTEGER REFERENCES wzory,
                wydanie_numer TEXT, wydanie_rok INTEGER, wydanie_naklad INTEGER,
                wydanie_tag TEXT, wydanie_cenzura TEXT, cenzura_id INTEGER REFERENCES cenzura,
                wydanie_zamowienie TEXT, awers_id INTEGER, rewers_id INTEGER
            );
            INSERT INTO miasta VALUES (1, 'Lublin', TRUE), (2, 'Kraków', FALSE);
            INSERT INTO autorzy (autor_id, autor_nazwa) VALUES (1, 'Jan Kowalski'), (2, 'Anna Nowak');
            INSERT INTO wydawcy VALUES (1, 'Wydawca demonstracyjny');
            INSERT INTO cenzura VALUES (1, 'D1');
            INSERT INTO wzory VALUES (1, 'Panorama Lublina', 'A1', 1, 1, 1),
                                     (2, 'Rynek w Krakowie', 'B1', 2, 2, 1);
        """)
        db.executemany(
            """INSERT INTO wydanie
                  (wydanie_id, wzor_id, wydanie_numer, wydanie_rok, wydanie_tag, awers_id, rewers_id)
               VALUES (?, ?, ?, 1965, ?, ?, ?)""",
            [(index, 1 if index <= 10 else 2, f'D{index}', 'panorama',
              1 if index == 1 else None, 2 if index == 1 else None)
             for index in range(1, 13)],
        )

    for number, color in ((1, 'navy'), (2, 'beige')):
        with Image.new('RGB', (240, 144), color) as image:
            image.save(root / 'images' / f'{number}.jpg')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path, help='nowy katalog danych')
    args = parser.parse_args()
    try:
        create_demo_data(args.folder)
    except FileExistsError:
        parser.exit(1, f'Katalog już istnieje: {args.folder}\n')
