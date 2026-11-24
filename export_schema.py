"""Eksport definicji tabel, indeksów, widoków i wyzwalaczy SQLite bez rekordów."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def export_schema(database, output):
    database = Path(database).resolve()
    output = Path(output).resolve()
    if database == output:
        raise ValueError('Plik wyjściowy musi być inny niż plik bazy.')
    # Tryb tylko do odczytu nie tworzy pustej bazy po błędzie w ścieżce.
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute("""
            SELECT type, name, sql FROM sqlite_schema
            WHERE sql IS NOT NULL AND substr(name, 1, 7) != 'sqlite_'
            ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1
                               WHEN 'view' THEN 2 ELSE 3 END, name
        """).fetchall()
    text = '-- Schemat SQLite: definicje obiektów, bez rekordów.\n'
    text += '-- Wewnętrzne obiekty sqlite_* są pomijane.\n\n'
    text += '\n\n'.join(sql.rstrip().rstrip(';') + ';' for _, _, sql in rows) + '\n'
    # Istniejącego pliku nie nadpisujemy: eksport może być cenną dokumentacją.
    with output.open('x', encoding='utf-8') as stream:
        stream.write(text)
    return len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path, help='plik aktualnej bazy pocztowki.db')
    parser.add_argument('output', type=Path, help='nowy plik SQL, np. schema.sql')
    args = parser.parse_args()
    try:
        count = export_schema(args.database, args.output)
    except (sqlite3.Error, OSError, ValueError) as error:
        parser.exit(1, f'Nie udało się wyeksportować schematu: {error}\n')
    print(f'Zapisano definicje {count} obiektów do {args.output}.')
