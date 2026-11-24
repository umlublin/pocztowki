import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from export_schema import export_schema


class ExportSchemaTest(unittest.TestCase):
    def test_exports_definitions_without_records_and_keeps_database_unchanged(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / 'baza #1.db'
            output = Path(directory) / 'schema.sql'
            with closing(sqlite3.connect(database)) as db, db:
                db.executescript("""
                    CREATE TABLE autorzy (autor_id INTEGER PRIMARY KEY, aliases TEXT);
                    CREATE INDEX autor_aliases ON autorzy(aliases);
                    CREATE VIEW fotografowie AS SELECT aliases FROM autorzy;
                    CREATE TRIGGER normalize_aliases AFTER INSERT ON autorzy
                    BEGIN UPDATE autorzy SET aliases=trim(aliases) WHERE autor_id=new.autor_id; END;
                    INSERT INTO autorzy VALUES (1, 'private-record-value');
                """)
            before = database.read_bytes()
            self.assertEqual(export_schema(database, output), 4)
            sql = output.read_text(encoding='utf-8')
            self.assertNotIn('private-record-value', sql)
            with closing(sqlite3.connect(':memory:')) as restored:
                restored.executescript(sql)
                self.assertEqual(restored.execute('SELECT * FROM autorzy').fetchall(), [])
                self.assertEqual(len(restored.execute('SELECT * FROM sqlite_schema WHERE sql IS NOT NULL').fetchall()), 4)
            self.assertEqual(database.read_bytes(), before)
            with self.assertRaises(FileExistsError):
                export_schema(database, output)
            with self.assertRaises(ValueError):
                export_schema(database, database)
            missing = Path(directory) / 'missing.db'
            with self.assertRaises(sqlite3.OperationalError):
                export_schema(missing, Path(directory) / 'missing.sql')
            self.assertFalse(missing.exists())
