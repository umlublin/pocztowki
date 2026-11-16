"""Dodaj pole alias do istniejącej bazy, zachowując dane fotografów."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def migrate(database):
    # mode=rw chroni przed utworzeniem pustej bazy po podaniu błędnej ścieżki.
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=rw', uri=True)) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            columns = {row[1].casefold() for row in db.execute('PRAGMA table_info(autorzy)')}
            if not columns:
                raise ValueError('W bazie nie ma tabeli autorzy.')
            if 'alias' not in columns:
                db.execute('ALTER TABLE autorzy ADD COLUMN alias TEXT')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path, help='ścieżka do pliku pocztowki.db')
    args = parser.parse_args()
    migrate(args.database)
    print('Tabela autorzy zawiera kolumnę alias. Dane zostały zachowane.')
