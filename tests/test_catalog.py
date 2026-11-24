import io
import os
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from PIL import Image

import server
from demo_data import create_demo_data
from migrate_authors import migrate


class CatalogTest(unittest.TestCase):
    def setUp(self):
        cleanup = ExitStack()
        self.addCleanup(cleanup.close)
        root = Path(cleanup.enter_context(TemporaryDirectory())) / 'demo'
        create_demo_data(root)
        self.database = root / 'instance' / 'pocztowki.db'
        self.images = root / 'images'
        self.thumbs = self.images / 'thumbnails'
        cleanup.enter_context(patch.multiple(
            server, DATABASE=self.database, IMAGE_FOLDER=self.images,
            THUMB_FOLDER=self.thumbs, admins={'demo-admin'},
        ))
        cleanup.enter_context(patch.dict(server.app.config, TESTING=True, SECRET_KEY='test-only'))
        self.client = server.app.test_client()
        self.edit = {
            'wydanie_numer': 'Nowy numer', 'wzor_opis': 'Nowy opis', 'wydanie_tag': 'kolor',
            'wydanie_rok': '1970', 'miasto_id': '2', 'autor_id': '2', 'wydawca_id': '1',
        }

    def login(self, user_id):
        with self.client.session_transaction() as session:
            session['user'] = {'userinfo': {'sub': user_id, 'nickname': 'Jan & Ola'}}

    def post_scans(self, *names):
        return self.client.post('/api/cards/import', data={
            'files': [(io.BytesIO((self.images / '1.jpg').read_bytes()), name) for name in names],
        })

    def test_import_pairs_reuses_pattern_and_numbers_files(self):
        front = 'prl_1337 Fragment parku.jpg'
        reverse = 'prl_1338 27-6 0 A-43 +Puławy @E.Hartwig.jpg'
        self.assertEqual(self.post_scans(front, reverse).status_code, 403)
        self.login('demo-admin')
        self.database.unlink()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript((Path(server.app.root_path) / 'schema.sql').read_text(encoding='utf-8'))
            db.execute("INSERT INTO autorzy (autor_id, autor_nazwa, aliases) VALUES (1, 'Edward Hartwig', 'E.Hartwig')")
            db.execute("""INSERT INTO miasta (miasto_id, miasto_nazwa, "default")
                          VALUES (1, 'Lublin', 1), (3, 'Puławy', 0)""")
            db.execute("INSERT INTO wydawcy VALUES (27, 'Wydawca')")
            db.execute("INSERT INTO cenzura (cenzura_id, cenzura_numer, year_from) VALUES (2, 'A-43', '1960')")
        (self.images / '9.jpg').write_bytes(b'existing scan')
        response = self.post_scans(
            'inne_1342 27-7 5k A-43 @E.Hartwig.jpg', reverse,
            'inne_1341 Panorama.jpg', front,
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        first, second = response.get_json()['wydania']
        first_card = self.client.get(f'/api/card/{first}').get_json()
        second_card = self.client.get(f'/api/card/{second}').get_json()
        self.assertEqual(
            [first_card[key] for key in ('wzor_numer', 'wzor_opis', 'miasto_id', 'autor_id',
                                         'wydawca_id', 'cenzura_id', 'wydanie_naklad', 'awers_id', 'rewers_id')],
            [6, 'Fragment parku', 3, 1, 27, 2, 0, 10, 11],
        )
        self.assertEqual((second_card['miasto_id'], second_card['wydanie_naklad']), (1, 5000))
        self.assertEqual((self.images / '9.jpg').read_bytes(), b'existing scan')
        self.assertTrue(all((self.images / f'{number}.jpg').exists() for number in range(10, 14)))
        response = self.post_scans('prl_1337 Inny opis.jpg', reverse)
        self.assertEqual(response.status_code, 201)
        repeated = self.client.get(f"/api/card/{response.get_json()['wydania'][0]}").get_json()
        self.assertEqual(repeated['wzor_id'], first_card['wzor_id'])
        self.assertEqual(repeated['wzor_opis'], 'Fragment parku')

    def test_import_rolls_back_batch_when_later_pair_fails(self):
        self.login('demo-admin')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE autorzy SET alias = 'J.K.' WHERE autor_id = 1")
        response = self.post_scans(
            'scan1 Opis.jpg', 'scan2 1-1 1000 D1 @J.K..jpg',
            'scan3 Opis.jpg', 'scan4 1-2 0 D1 @Brak.jpg',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Brak', response.get_json()['error'])
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM wydanie').fetchone()[0], 12)
            self.assertEqual(db.execute('SELECT count(*) FROM wzory').fetchone()[0], 2)
        self.assertEqual({path.name for path in self.images.glob('*.jpg')}, {'1.jpg', '2.jpg'})

    def test_town_permissions_and_shared_data(self):
        data = {'miasto_nazwa': ' Nowy Lublin '}
        self.assertEqual(self.client.get('/towns').status_code, 200)
        self.assertNotIn(b'/towns/1/edit', self.client.get('/towns').data)
        for user in (None, 'other'):
            if user:
                self.login(user)
            self.assertEqual(self.client.get('/towns/1/edit').status_code, 403)
            self.assertEqual(self.client.put('/api/towns/1', json=data).status_code, 403)
        self.login('demo-admin')
        self.assertIn(b'/towns/1/edit', self.client.get('/towns').data)
        self.assertEqual(self.client.get('/towns/1/edit').status_code, 200)
        self.assertEqual(self.client.put('/api/towns/1', json=data).status_code, 200)
        for card_id in (1, 2):
            card = self.client.get(f'/api/card/{card_id}').get_json()
            self.assertEqual((card['miasto_id'], card['miasto_nazwa']), (1, 'Nowy Lublin'))
        self.assertIn({'miasto_id': 1, 'miasto_nazwa': 'Nowy Lublin'},
                      self.client.get('/api/filters').get_json()['miasta'])
        self.assertEqual(self.client.get('/api/card/12').get_json()['miasto_nazwa'], 'Kraków')
        self.assertEqual(len(self.client.get('/api/search?miasto_id=1').get_json()), 10)
        for path in ('/', '/view/1', '/photographers'):
            self.assertIn(b'href="/towns"', self.client.get(path).data)

    def test_town_search_escaping_and_validation(self):
        self.login('demo-admin')
        for data in (None, [], {}, {'miasto_nazwa': None}, {'miasto_nazwa': 1},
                     {'miasto_nazwa': ''}, {'miasto_nazwa': ' '}, {'miasto_nazwa': 'x'*201}):
            self.assertEqual(self.client.put('/api/towns/1', json=data).status_code, 400)
        self.assertEqual(self.client.put('/api/towns/1', json={'miasto_nazwa': ' kRAKÓW '}).status_code, 409)
        self.assertEqual(self.client.get('/api/card/1').get_json()['miasto_nazwa'], 'Lublin')
        self.assertEqual(self.client.get('/towns/999/edit').status_code, 404)
        self.assertEqual(self.client.put('/api/towns/999', json={'miasto_nazwa': 'Test'}).status_code, 404)
        self.assertEqual(self.client.put('/api/towns/1', json={'miasto_nazwa': 'Łódź'}).status_code, 200)
        # Ponowny zapis własnej nazwy nie jest duplikatem.
        self.assertEqual(self.client.put('/api/towns/1', json={'miasto_nazwa': 'Łódź'}).status_code, 200)
        page = self.client.get('/towns', query_string={'q': ' łÓDŹ '}).get_data(as_text=True)
        self.assertIn('Łódź', page)
        self.assertNotIn('Kraków', page)
        self.assertIn('/?miasto_id=1', page)
        self.assertIn('Nie znaleziono miejscowości.', self.client.get('/towns?q=brak').get_data(as_text=True))
        name = '<script>alert(1)</script>'
        self.assertEqual(self.client.put('/api/towns/1', json={'miasto_nazwa': name}).status_code, 200)
        for path in ('/towns', '/towns/1/edit'):
            page = self.client.get(path).get_data(as_text=True)
            self.assertIn('&lt;script&gt;', page)
            self.assertNotIn(name, page)

    def test_town_write_failure_preserves_data(self):
        self.login('demo-admin')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("CREATE TRIGGER reject_town BEFORE UPDATE ON miasta BEGIN SELECT RAISE(ABORT, 'test'); END;")
        self.assertEqual(self.client.put('/api/towns/1', json={'miasto_nazwa': 'Test'}).status_code, 500)
        self.assertEqual(self.client.get('/api/card/1').get_json()['miasto_nazwa'], 'Lublin')

    def test_photographer_edit_permissions_and_shared_data(self):
        data = {'autor_nazwa': 'Jan Fotograf', 'alias': 'J. Fotograf',
                'autor_lata': '1890–1965', 'autor_url': 'https://example.org/biogram'}
        self.assertEqual(self.client.get('/photographers').status_code, 200)
        self.assertNotIn(b'/photographers/1/edit', self.client.get('/photographers').data)
        for user in (None, 'other'):
            if user:
                self.login(user)
            self.assertEqual(self.client.get('/photographers/1/edit').status_code, 403)
            self.assertEqual(self.client.put('/api/photographers/1', json=data).status_code, 403)
        self.login('demo-admin')
        self.assertIn(b'/photographers/1/edit', self.client.get('/photographers').data)
        self.assertEqual(self.client.get('/photographers/1/edit').status_code, 200)
        self.assertEqual(self.client.put('/api/photographers/1', json=data).status_code, 200)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute(
                'SELECT autor_nazwa, alias, autor_lata, autor_url FROM autorzy WHERE autor_id=1'
            ).fetchone(), tuple(data.values()))
            self.assertEqual(db.execute('SELECT autor_nazwa FROM autorzy WHERE autor_id=2').fetchone()[0], 'Anna Nowak')
        for card_id in (1, 2):
            card = self.client.get(f'/api/card/{card_id}').get_json()
            self.assertEqual(card['autor_nazwa'], data['autor_nazwa'])
            self.assertEqual(card['autor_lata'], data['autor_lata'])
            self.assertEqual(card['autor_url'], data['autor_url'])
        page = self.client.get('/photographers?q=j.+FOTOGRAF').get_data(as_text=True)
        self.assertIn('Jan Fotograf', page)
        self.assertNotIn('Anna Nowak', page)
        self.assertIn('https://example.org/biogram', page)
        self.assertIn('/?autor_id=1', page)
        for path in ('/', '/view/1'):
            self.assertIn(b'href="/photographers"', self.client.get(path).data)

    def test_photographer_validation_and_clear_optional_fields(self):
        self.login('demo-admin')
        data = {'autor_nazwa': ' Jan ', 'alias': '', 'autor_lata': '', 'autor_url': ''}
        for invalid in (None, [], {}, {**data, 'autor_nazwa': ' '},
                        {**data, 'alias': 123}, {**data, 'autor_lata': 'x'*101},
                        {**data, 'autor_nazwa': 'x'*201}, {**data, 'autor_url': 'x'*2049}):
            self.assertEqual(self.client.put('/api/photographers/1', json=invalid).status_code, 400)
        for url in ('javascript:alert(1)', '//example.org', 'https://', 'https://[bad',
                    'https://example.org:bad', 'https://user:pass@example.org', 'https://exa mple.org'):
            self.assertEqual(self.client.put('/api/photographers/1', json={**data, 'autor_url': url}).status_code, 400)
        self.assertEqual(self.client.get('/photographers/999/edit').status_code, 404)
        self.assertEqual(self.client.put('/api/photographers/999', json=data).status_code, 404)
        self.assertEqual(self.client.put('/api/photographers/1', json=data).status_code, 200)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT autor_nazwa, alias, autor_lata, autor_url FROM autorzy WHERE autor_id=1').fetchone(), ('Jan', None, None, None))

    def test_photographer_html_escaping_and_empty_search(self):
        self.login('demo-admin')
        data = {'autor_nazwa': '<script>alert(1)</script>', 'alias': '<img src=x onerror=alert(1)>',
                'autor_lata': '1900–?', 'autor_url': ''}
        self.assertEqual(self.client.put('/api/photographers/1', json=data).status_code, 200)
        for path in ('/photographers', '/photographers/1/edit'):
            page = self.client.get(path).get_data(as_text=True)
            self.assertIn('&lt;script&gt;', page)
            self.assertNotIn('<script>alert(1)</script>', page)
            self.assertNotIn('<img src=x', page)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE autorzy SET autor_url='javascript:alert(1)' WHERE autor_id=1")
        self.assertNotIn(b'href="javascript:', self.client.get('/photographers').data)
        self.assertIn('Nie znaleziono fotografów.', self.client.get('/photographers?q=brak').get_data(as_text=True))

    def test_author_alias_migration_preserves_legacy_database(self):
        legacy = self.database.parent / 'legacy.db'
        with closing(sqlite3.connect(legacy)) as db, db:
            db.execute('CREATE TABLE autorzy (autor_id INTEGER PRIMARY KEY, autor_nazwa TEXT, autor_lata TEXT, autor_url TEXT)')
            db.execute("INSERT INTO autorzy VALUES (7, 'Fotograf', '1900–1980', 'https://example.org')")
        migrate(legacy)
        migrate(legacy)
        with closing(sqlite3.connect(legacy)) as db:
            self.assertEqual(db.execute('SELECT * FROM autorzy').fetchall(),
                             [(7, 'Fotograf', '1900–1980', 'https://example.org', None)])
        missing = legacy.parent / 'missing.db'
        with self.assertRaises(sqlite3.OperationalError):
            migrate(missing)
        self.assertFalse(missing.exists())

    def test_search_pages_filters_and_ties(self):
        page = self.client.get('/api/search?sort=').get_json()
        self.assertEqual([row['wydanie_id'] for row in page], list(range(1, 11)))
        page = self.client.get('/api/search?offset=10').get_json()
        self.assertEqual([row['wydanie_id'] for row in page], [11, 12])
        page = self.client.get('/api/search?wydawca_id=1&wzor_numer=B1&miasto_id=2').get_json()
        self.assertEqual([row['wydanie_id'] for row in page], [11, 12])
        page = self.client.get('/api/search?q=Panorama&autor_id=1&rok=1965').get_json()
        self.assertEqual(len(page), 10)
        self.assertEqual(self.client.get('/api/filters').get_json()['miasta'][0]['miasto_nazwa'], 'Kraków')

    def test_details_have_neighbours_at_both_boundaries(self):
        first = self.client.get('/api/card/1').get_json()
        last = self.client.get('/api/card/12').get_json()
        self.assertEqual((first['prev_id'], first['next_id']), (None, 2))
        self.assertEqual((last['prev_id'], last['next_id']), (11, None))
        self.assertEqual(self.client.get('/api/card/13').status_code, 404)

    def test_auth0_redirect_urls(self):
        with patch.multiple(
            server, MY_URL='http://localhost:5000', AUTH0_DOMAIN='test.example',
            AUTH0_CLIENT_ID='client', AUTH0_CLIENT_SECRET='secret',
        ), patch.object(server, 'oauth') as oauth:
            oauth.auth0.authorize_redirect.return_value = ('', 302)
            self.assertEqual(self.client.get('/login').status_code, 302)
            oauth.auth0.authorize_redirect.assert_called_once_with(
                redirect_uri='http://localhost:5000/callback'
            )
            response = self.client.get('/logout')
            url = urlsplit(response.location)
            self.assertEqual(url.netloc, 'test.example')
            self.assertEqual(parse_qs(url.query)['returnTo'], ['http://localhost:5000/'])

    def test_permissions_and_valid_update(self):
        self.assertEqual(self.client.put('/api/card/1', json=self.edit).status_code, 403)
        self.assertIn(b'href="/login"', self.client.get('/').data)
        self.login('other')
        self.assertEqual(self.client.put('/api/card/1', json=self.edit).status_code, 403)
        self.assertIn(b'btn-edit-toggle" hidden', self.client.get('/view/1').data)
        self.login('demo-admin')
        for path in ('/', '/view/1'):
            self.assertIn(b'Jan &amp; Ola', self.client.get(path).data)
        self.assertNotIn(b'btn-edit-toggle" hidden', self.client.get('/view/1').data)
        self.assertEqual(self.client.put('/api/card/1', json={**self.edit, 'miasto_id': 99}).status_code, 400)
        self.assertEqual(self.client.put('/api/card/1', json=self.edit).status_code, 200)
        updated = self.client.get('/api/card/1').get_json()
        sibling = self.client.get('/api/card/2').get_json()
        self.assertEqual((updated['wydanie_numer'], updated['wydanie_rok']), ('Nowy numer', 1970))
        self.assertEqual((sibling['wydanie_numer'], sibling['wzor_opis']), ('D2', 'Nowy opis'))

    def test_edit_rolls_back_when_pattern_update_fails(self):
        self.login('demo-admin')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("""
                CREATE TRIGGER reject_edit BEFORE UPDATE ON wzory
                BEGIN SELECT RAISE(ABORT, 'test rejected update'); END;
            """)
        response = self.client.put('/api/card/1', json=self.edit)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('test rejected update', response.get_json()['error'])
        self.assertEqual(self.client.get('/api/card/1').get_json()['wydanie_numer'], 'D1')

    def test_dictionary_create_reuses_existing_name(self):
        path = '/api/dictionaries/miasta'
        self.assertEqual(self.client.post(path, json={'name': 'Łódź'}).status_code, 403)
        self.login('demo-admin')
        self.assertEqual(self.client.post(path, json={'name': '  '}).status_code, 400)
        result = self.client.post(path, json={'name': ' Łódź '})
        self.assertEqual(result.status_code, 201)
        entry = result.get_json()
        duplicate = self.client.post(path, json={'name': 'ŁÓDŹ'})
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.get_json(), entry)
        self.assertIn(entry, self.client.get('/api/filters').get_json()['miasta'])
        self.assertEqual(self.client.put('/api/card/1', json={
            **self.edit, 'miasto_id': entry['miasto_id'],
        }).status_code, 200)
        self.assertEqual(self.client.get('/api/card/2').get_json()['miasto_nazwa'], 'Łódź')

    def test_extended_fields_and_exact_filters(self):
        self.login('demo-admin')
        extra = {
            'wydanie_naklad': '1000', 'wydanie_cenzura': 'Zatwierdzona', 'cenzura_id': '1',
            'wzor_numer': 'A2',
        }
        self.assertEqual(self.client.put('/api/card/1', json={
            **self.edit, **extra, 'cenzura_id': '99',
        }).status_code, 400)
        self.assertEqual(self.client.put('/api/card/1', json={
            **self.edit, **extra, 'wydanie_tag': 'panoramiczny, Kolor  , ramka',
        }).status_code, 200)
        self.assertEqual(self.client.get('/api/search?tag=panorama&cenzura_id=1').get_json(), [])
        result = self.client.get('/api/search?tag=KOLOR&rok=1970&cenzura_id=1').get_json()
        self.assertEqual([row['wydanie_id'] for row in result], [1])
        self.assertEqual(result[0]['wydanie_naklad'], 1000)
        self.assertEqual(self.client.get('/api/card/2').get_json()['wzor_numer'], 'A2')
        # Aktualizacja starym formatem żądania zachowuje pola dodane później.
        self.assertEqual(self.client.put('/api/card/1', json=self.edit).status_code, 200)
        saved = self.client.get('/api/card/1').get_json()
        self.assertEqual((saved['wydanie_naklad'], saved['cenzura_numer'], saved['wzor_numer']),
                         (1000, 'D1', 'A2'))

    def test_thumbnail_cache_concurrency_refresh_and_missing_image(self):
        def read_thumbnail():
            with server.app.test_client() as client, client.get('/images/1_mini.jpg') as response:
                self.assertEqual(response.status_code, 200)
                return response.data

        with ThreadPoolExecutor(max_workers=4) as pool:
            images = list(pool.map(lambda _: read_thumbnail(), range(4)))
        self.assertTrue(all(image == images[0] for image in images))
        self.assertEqual(len(list(self.thumbs.iterdir())), 1)
        with Image.open(io.BytesIO(images[0])) as image:
            self.assertEqual(image.size, (120, 72))
        replacement = self.images / 'replacement.jpg'
        with Image.new('RGB', (144, 240), 'orange') as image:
            image.save(replacement)
        os.replace(replacement, self.images / '1.jpg')
        with Image.open(io.BytesIO(read_thumbnail())) as image:
            self.assertEqual(image.size, (72, 120))
        (self.images / '1.jpg').unlink()
        self.assertEqual(self.client.get('/images/1_mini.jpg').status_code, 404)
        with self.client.get('/icons/icons8-login-32.png') as response:
            self.assertEqual(response.status_code, 200)
