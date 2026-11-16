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
