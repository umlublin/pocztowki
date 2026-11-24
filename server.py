from logging.handlers import RotatingFileHandler
import logging
from urllib.parse import quote_plus, urlencode, urlsplit
from authlib.integrations.flask_client import OAuth
import sqlite3
import os
import re
from tempfile import NamedTemporaryFile
from os import environ as env
from flask import Flask, redirect, render_template, request, g, send_from_directory, abort, jsonify,session
from PIL import Image
from waitress import serve
from dotenv import find_dotenv, load_dotenv

ENV_FILE = find_dotenv()
if ENV_FILE:
    print("Load .env values from", ENV_FILE)
    load_dotenv(ENV_FILE)

MY_URL = env.get("MY_URL", "").rstrip("/")
AUTH0_DOMAIN = env.get("AUTH0_DOMAIN")
AUTH0_CLIENT_ID = env.get("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = env.get("AUTH0_CLIENT_SECRET")
DATA_ROOT = os.path.abspath(env.get("DATA_ROOT", "."))

admins = {sid for sid in (env.get('ADMIN_SID'), env.get('ADMIN_SID_BACKUP')) if sid}

SEARCH_SORT_FIELDS = {
    'wydanie_rok': ('Rok wydania', 'wyd.wydanie_rok'),
    'wzor_numer': ('Numer', 'wz.wzor_numer'),
    'miasto_nazwa': ('Miasto', 'm.miasto_nazwa'),
    'autor_nazwa': ('Autor', 'a.autor_nazwa'),
    'wydawca_nazwa': ('Wydawca', 'pub.wydawca_nazwa'),
}
SQLITE_MAX_INTEGER = 2**63 - 1
EDITABLE_DICTIONARIES = {
    'miasta': ('miasto_id', 'miasto_nazwa'),
    'autorzy': ('autor_id', 'autor_nazwa'),
    'wydawcy': ('wydawca_id', 'wydawca_nazwa'),
}

file_handler = RotatingFileHandler(os.path.join(env.get("LOG_ROOT", "./"), "pocztowka_app.log"), maxBytes=1024000, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s'
))
file_handler.setLevel(logging.INFO)

app = Flask(__name__)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

app.secret_key = env.get("APP_SECRET_KEY")


DATABASE = os.path.join(DATA_ROOT, 'instance/pocztowki.db')
IMAGE_FOLDER = os.path.join(DATA_ROOT, 'images')
THUMB_FOLDER = os.path.join(IMAGE_FOLDER, 'thumbnails')
ICON_FOLDER = os.path.join(app.root_path, 'icons')
THUMB_SIZE = 120  # Max szerokość/wysokość w pikselach

oauth = OAuth(app)

oauth.register(
    "auth0",
    client_id=AUTH0_CLIENT_ID,
    client_secret=AUTH0_CLIENT_SECRET,
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f'https://{AUTH0_DOMAIN}/.well-known/openid-configuration'
)

def get_user_data():
    userinfo = (session.get('user') or {}).get('userinfo') or {}
    if not userinfo:
        return {}
    return {**userinfo, 'is_admin': userinfo.get('sub') in admins}

def has_tag(tags, requested_tag):
    return any(tag.strip().casefold() == requested_tag for tag in str(tags or '').split(','))


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.create_function('has_tag', 2, has_tag)
    return db

@app.before_request
def log_request_info():
    # app.logger.info('Headers: %s', request.headers)
    # app.logger.info('Body: %s', request.get_data())
    email = get_user_data().get("email", "")
    ip = request.headers.get('X-Real-Ip', '0.0.0.0')
    app.logger.info('%s (%s) %s %s', ip, email, request.method, request.path)


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route("/login")
def login():
    if not all((MY_URL, AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, app.secret_key)):
        abort(503, description='Logowanie nie jest skonfigurowane.')
    return oauth.auth0.authorize_redirect(redirect_uri=f'{MY_URL}/callback')


@app.route("/callback", methods=["GET", "POST"])
def callback():
    token = oauth.auth0.authorize_access_token()
    session["user"] = token
    return redirect("/")        

@app.route("/logout")
def logout():
    session.clear()
    if not all((MY_URL, AUTH0_DOMAIN, AUTH0_CLIENT_ID)):
        return redirect("/")
    return redirect(
        "https://" + AUTH0_DOMAIN
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": f'{MY_URL}/',
                "client_id": AUTH0_CLIENT_ID,
            },
            quote_via=quote_plus,
        )
    )

@app.route("/api/userdata.json")
def userdata():
    return jsonify(get_user_data())

# Helper do konwersji wierszy DB na dict (dla JSON)
def dict_from_row(row):
    return dict(zip(row.keys(), row))


def dict_list_from_rows(rows):
    return [dict_from_row(r) for r in rows]


@app.route('/icons/<path:path>')
def send_icons(path):
    return send_from_directory(ICON_FOLDER, path)

@app.route('/images/<int:img_id>.jpg')
def serve_original_image(img_id):
    """Serwuje pełny obrazek"""
    return send_from_directory(IMAGE_FOLDER, f"{img_id}.jpg")


@app.route('/images/<int:img_id>_mini.jpg')
def serve_thumbnail(img_id):
    """Generuje, cachuje i serwuje miniaturkę"""
    original_path = os.path.join(IMAGE_FOLDER, f"{img_id}.jpg")
    temp_path = None
    try:
        with open(original_path, 'rb') as original:
            stat = os.fstat(original.fileno())
            version = f'{stat.st_ino:x}-{stat.st_mtime_ns:x}-{stat.st_ctime_ns:x}-{stat.st_size:x}'
            thumb_filename = f'{img_id}_{version}_mini.jpg'
            thumb_path = os.path.join(THUMB_FOLDER, thumb_filename)
            if not os.path.exists(thumb_path):
                os.makedirs(THUMB_FOLDER, exist_ok=True)
                with Image.open(original) as img:
                    img.thumbnail((THUMB_SIZE, THUMB_SIZE))
                    with NamedTemporaryFile(dir=THUMB_FOLDER, delete=False) as temp:
                        temp_path = temp.name
                        img.convert('RGB').save(temp, 'JPEG', quality=85)

                final_stat = os.fstat(original.fileno())
                if (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size) != (
                    final_stat.st_mtime_ns, final_stat.st_ctime_ns, final_stat.st_size
                ):
                    abort(503, description='Skan zmienił się podczas odczytu. Spróbuj ponownie.')
                os.replace(temp_path, thumb_path)
                temp_path = None
    except FileNotFoundError:
        abort(404)
    except (OSError, Image.DecompressionBombError):
        app.logger.exception('Nie udało się odczytać lub zapisać miniatury %s', img_id)
        abort(500)
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    return send_from_directory(THUMB_FOLDER, thumb_filename)


@app.route('/api/filters')
def api_filters():
    """Zwraca dane do selectów"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT miasto_id, miasto_nazwa FROM miasta ORDER BY miasto_nazwa ASC")
    cities = dict_list_from_rows(cursor.fetchall())

    cursor.execute("SELECT autor_id, autor_nazwa FROM autorzy ORDER BY autor_nazwa ASC")
    authors = dict_list_from_rows(cursor.fetchall())

    cursor.execute("SELECT wydawca_id, wydawca_nazwa FROM wydawcy ORDER BY wydawca_nazwa ASC")
    publishers = dict_list_from_rows(cursor.fetchall())

    cursor.execute("SELECT cenzura_id, cenzura_numer FROM cenzura ORDER BY cenzura_numer ASC")
    cenzura = dict_list_from_rows(cursor.fetchall())

    return jsonify({
        'miasta': cities,
        'autorzy': authors,
        'wydawcy': publishers,
        'cenzura': cenzura,
        'tagi': ['panorama', 'kolor', 'ramka', 'lotnicze'],
        'sort': [{'field_id': key, 'field_name': label}
                 for key, (label, _) in SEARCH_SORT_FIELDS.items()]
    })


@app.route('/api/dictionaries/<kind>', methods=['POST'])
def create_dictionary_entry(kind):
    if not get_user_data().get('is_admin'):
        return jsonify({'error': 'Edycja wymaga uprawnień administratora.'}), 403
    fields = EDITABLE_DICTIONARIES.get(kind)
    if fields is None:
        abort(404)

    data = request.get_json(silent=True)
    name = data.get('name') if isinstance(data, dict) else None
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        return jsonify({'error': 'Podaj nazwę o długości od 1 do 200 znaków.'}), 400
    name = name.strip()
    id_field, name_field = fields

    try:
        conn = get_db()
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            # Dopasowanie Unicode również dla polskich nazw.
            normalized_name = name.casefold()
            for row in conn.execute(f'SELECT {id_field}, {name_field} FROM {kind} ORDER BY {id_field}'):
                if row[name_field] and row[name_field].strip().casefold() == normalized_name:
                    return jsonify(dict_from_row(row)), 200
            inserted = conn.execute(f'INSERT INTO {kind} ({name_field}) VALUES (?)', (name,))
            entry = conn.execute(
                f'SELECT {id_field}, {name_field} FROM {kind} WHERE {id_field} = ?',
                (inserted.lastrowid,),
            ).fetchone()
            if entry is None:
                raise sqlite3.IntegrityError('Dictionary key was not assigned')
            return jsonify(dict_from_row(entry)), 201
    except sqlite3.Error:
        app.logger.exception('Nie udało się dodać wpisu do słownika %s', kind)
        return jsonify({'error': 'Nie udało się zapisać wpisu słownikowego.'}), 500


@app.route('/api/search')
def api_search():
    """Zwraca listę pocztówek wg filtrów"""
    query = request.args.get('q', '')
    rok_filter = request.args.get('rok', type=int)
    miasto_filter = request.args.get('miasto_id', type=int)
    autor_filter = request.args.get('autor_id', type=int)
    wydawca_filter = request.args.get('wydawca_id', type=int)
    wzor_numer = request.args.get('wzor_numer', type=str)
    cenzura_id = request.args.get('cenzura_id', type=int)
    tag = request.args.get('tag', '').strip().casefold()
    sort_filter = request.args.get('sort', type=str, default='wydanie_rok')
    offset = request.args.get('offset', type=int, default=0)
    if any(value is not None and not 0 <= value <= SQLITE_MAX_INTEGER
           for value in (rok_filter, miasto_filter, autor_filter, wydawca_filter, cenzura_id)):
        return jsonify({'error': 'Wartość filtra poza dozwolonym zakresem.'}), 400
    if not 0 <= offset <= SQLITE_MAX_INTEGER:
        return jsonify({'error': 'Przesunięcie wyników poza dozwolonym zakresem.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    sql = """
          SELECT wyd.wydanie_id, \
                 wyd.wydanie_numer, \
                 wyd.wydanie_rok, \
                 wyd.wydanie_naklad, \
                 wyd.wydanie_tag, \
                 wyd.wydanie_cenzura, \
                 wyd.wydanie_zamowienie, \
                 wyd.awers_id, \
                 wyd.rewers_id, \
                 wz.wzor_id, \
                 wz.wzor_opis, \
                 wz.wydawca_id, \
                 wz.wzor_numer, \
                 (coalesce(wz.wydawca_id, '') || '-' || coalesce(wz.wzor_numer, '')) as wydawca_wzor_numer, \
                 wz.wzor_opis, \
                 m.miasto_nazwa, \
                 a.autor_nazwa
          FROM wydanie wyd
                   LEFT JOIN wzory wz ON wyd.wzor_id = wz.wzor_id
                   LEFT JOIN miasta m ON wz.miasto_id = m.miasto_id
                   LEFT JOIN autorzy a ON wz.autor_id = a.autor_id
                   LEFT JOIN wydawcy pub ON wz.wydawca_id = pub.wydawca_id
          WHERE 1 = 1 \
          """

    params = []

    if query:
        search_term = f"%{query}%"
        sql += " AND (wz.wzor_opis LIKE ? OR wz.wzor_numer LIKE ?)"
        params.extend([search_term, search_term])

    if rok_filter is not None:
        sql += " AND wyd.wydanie_rok = ?"
        params.append(rok_filter)

    if miasto_filter:
        sql += " AND wz.miasto_id = ?"
        params.append(miasto_filter)
    if autor_filter:
        sql += " AND wz.autor_id = ?"
        params.append(autor_filter)
    if wydawca_filter:
        sql += " AND wz.wydawca_id = ?"
        params.append(wydawca_filter)
    if wzor_numer:
        sql += " AND wz.wzor_numer = ?"
        params.append(wzor_numer)

    if cenzura_id:
        sql += " AND wyd.cenzura_id = ?"
        params.append(cenzura_id)
    if tag:
        sql += " AND has_tag(wyd.wydanie_tag, ?)"
        params.append(tag)

    _, sort_column = SEARCH_SORT_FIELDS.get(sort_filter, SEARCH_SORT_FIELDS['wydanie_rok'])
    sql += f" ORDER BY {sort_column}, wyd.wydanie_id LIMIT 10 OFFSET ?"
    params.append(offset)

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    return jsonify(dict_list_from_rows(rows))


@app.route('/api/card/<int:wydanie_id>')
def api_card_detail(wydanie_id):
    conn = get_db()
    cursor = conn.cursor()

    sql = """
          SELECT (SELECT max(wydanie_id) FROM wydanie WHERE wydanie_id < wyd.wydanie_id) AS prev_id,
                 (SELECT min(wydanie_id) FROM wydanie WHERE wydanie_id > wyd.wydanie_id) AS next_id,
                 wyd.*, \
                 wz.wzor_opis, \
                 wz.wydawca_id, \
                 wz.wzor_numer, \
                 m.miasto_id, \
                 m.miasto_nazwa,\
                 a.autor_id, \
                 a.autor_nazwa, \
                 a.autor_lata, \
                 a.autor_url, \
                 c.cenzura_numer, \
                 pub.wydawca_nazwa
          FROM wydanie wyd
                   LEFT JOIN wzory wz ON wyd.wzor_id = wz.wzor_id
                   LEFT JOIN miasta m ON wz.miasto_id = m.miasto_id
                   LEFT JOIN autorzy a ON wz.autor_id = a.autor_id
                   LEFT JOIN cenzura c ON wyd.cenzura_id = c.cenzura_id
                   LEFT JOIN wydawcy pub ON wz.wydawca_id = pub.wydawca_id
          WHERE wyd.wydanie_id = ? \
          """
    cursor.execute(sql, (wydanie_id,))
    row = cursor.fetchone()

    if row is None:
        return jsonify({'error': 'Pocztówka nie istnieje'}), 404

    return jsonify(dict_from_row(row))


def read_card_integer(data, field, minimum, empty_value):
    value = data[field]
    if value is None or value == '':
        return empty_value
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,19}', value):
        value = int(value)
    if type(value) is not int or not minimum <= value <= SQLITE_MAX_INTEGER:
        raise ValueError(f'Nieprawidłowa wartość pola {field}.')
    return value


@app.route('/towns')
def towns():
    query = request.args.get('q', '').strip()
    rows = get_db().execute(
        'SELECT miasto_id, miasto_nazwa FROM miasta ORDER BY miasto_nazwa, miasto_id'
    ).fetchall()
    if query:
        rows = [row for row in rows if query.casefold() in (row['miasto_nazwa'] or '').casefold()]
    return render_template('towns.html', towns=rows, query=query, user=get_user_data())


@app.route('/towns/<int:town_id>/edit')
def edit_town(town_id):
    if not get_user_data().get('is_admin'):
        abort(403)
    town = get_db().execute(
        'SELECT miasto_id, miasto_nazwa FROM miasta WHERE miasto_id = ?', (town_id,)
    ).fetchone()
    if town is None:
        abort(404)
    return render_template('town_edit.html', town=town, user=get_user_data())


@app.route('/api/towns/<int:town_id>', methods=['PUT'])
def update_town(town_id):
    if not get_user_data().get('is_admin'):
        return jsonify({'error': 'Edycja wymaga uprawnień administratora.'}), 403
    data = request.get_json(silent=True)
    name = data.get('miasto_nazwa') if isinstance(data, dict) else None
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        return jsonify({'error': 'Podaj nazwę miejscowości o długości od 1 do 200 znaków.'}), 400
    name = name.strip()
    try:
        conn = get_db()
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute('SELECT 1 FROM miasta WHERE miasto_id = ?', (town_id,)).fetchone() is None:
                return jsonify({'error': 'Miejscowość nie istnieje.'}), 404
            for row in conn.execute('SELECT miasto_nazwa FROM miasta WHERE miasto_id != ?', (town_id,)):
                if (row['miasto_nazwa'] or '').strip().casefold() == name.casefold():
                    return jsonify({'error': 'Miejscowość o tej nazwie już istnieje.'}), 409
            conn.execute('UPDATE miasta SET miasto_nazwa = ? WHERE miasto_id = ?', (name, town_id))
        return jsonify({'success': True})
    except sqlite3.Error:
        app.logger.exception('Nie udało się zapisać miejscowości %s', town_id)
        return jsonify({'error': 'Nie udało się zapisać miejscowości.'}), 500


@app.route('/photographers')
def photographers():
    query = request.args.get('q', '').strip()
    rows = get_db().execute(
        'SELECT autorzy.autor_id, autor_nazwa, aliases, autor_lata, autor_url, count(*) autor_count '
        'FROM autorzy JOIN wzory ON wzory.autor_id = autorzy.autor_id GROUP BY autorzy.autor_id '
        'ORDER BY autor_nazwa, autorzy.autor_id'
    ).fetchall()
    if query:
        rows = [row for row in rows if any(
            query.casefold() in (row[field] or '').casefold()
            for field in ('autor_nazwa', 'aliases')
        )]
    return render_template('photographers.html', authors=rows, query=query,
                           user=get_user_data())


@app.route('/photographers/<int:author_id>/edit')
def edit_photographer(author_id):
    if not get_user_data().get('is_admin'):
        abort(403)
    author = get_db().execute(
        'SELECT autor_id, autor_nazwa, aliases, autor_lata, autor_url '
        'FROM autorzy WHERE autor_id = ?', (author_id,)
    ).fetchone()
    if author is None:
        abort(404)
    return render_template('photographer_edit.html', author=author, user=get_user_data())


@app.route('/api/photographers/<int:author_id>', methods=['PUT'])
def update_photographer(author_id):
    if not get_user_data().get('is_admin'):
        return jsonify({'error': 'Edycja wymaga uprawnień administratora.'}), 403
    data = request.get_json(silent=True)
    limits = {'autor_nazwa': 200, 'aliases': 200, 'autor_lata': 100, 'autor_url': 2048}
    if not isinstance(data, dict):
        return jsonify({'error': 'Oczekiwano obiektu JSON z danymi fotografa.'}), 400
    values = {}
    for field, limit in limits.items():
        value = data.get(field)
        if not isinstance(value, str) or len(value.strip()) > limit:
            return jsonify({'error': f'Pole {field} musi być tekstem do {limit} znaków.'}), 400
        values[field] = value.strip()
    if not values['autor_nazwa']:
        return jsonify({'error': 'Podaj imię i nazwisko fotografa.'}), 400
    if values['autor_url']:
        try:
            url = urlsplit(values['autor_url'])
            if (url.scheme not in ('http', 'https') or not url.hostname
                    or url.username is not None or url.password is not None
                    or any(char.isspace() or ord(char) < 32 for char in values['autor_url'])):
                raise ValueError
            url.port  # Sprawdzenie poprawności portu.
        except ValueError:
            return jsonify({'error': 'Link do biogramu musi być poprawnym adresem HTTP lub HTTPS.'}), 400
    try:
        conn = get_db()
        with conn:
            updated = conn.execute(
                'UPDATE autorzy SET autor_nazwa = ?, aliases = ?, autor_lata = ?, autor_url = ? '
                'WHERE autor_id = ?',
                (values['autor_nazwa'], values['aliases'] or None,
                 values['autor_lata'] or None, values['autor_url'] or None, author_id),
            )
            if updated.rowcount != 1:
                return jsonify({'error': 'Fotograf nie istnieje.'}), 404
        return jsonify({'success': True})
    except sqlite3.Error:
        app.logger.exception('Nie udało się zapisać fotografa %s', author_id)
        return jsonify({'error': 'Nie udało się zapisać danych fotografa.'}), 500


@app.route('/api/card/<int:wydanie_id>', methods=['PUT'])
def api_card_update(wydanie_id):
    """Aktualizacja danych pocztówki przez administratora."""
    if not get_user_data().get('is_admin'):
        return jsonify({'error': 'Edycja wymaga uprawnień administratora.'}), 403

    data = request.get_json(silent=True)
    text_fields = ('wydanie_numer', 'wzor_opis', 'wydanie_tag')
    reference_fields = (
        ('miasto_id', 'miasta'),
        ('autor_id', 'autorzy'),
        ('wydawca_id', 'wydawcy'),
    )
    if not isinstance(data, dict):
        return jsonify({'error': 'Oczekiwano obiektu JSON z danymi edycji.'}), 400
    if 'cenzura_id' in data:
        reference_fields += (('cenzura_id', 'cenzura'),)

    try:
        for field in text_fields:
            if not isinstance(data.get(field), str):
                raise ValueError(f'Pole {field} jest wymagane i musi być tekstem.')
        for field in ('wydanie_cenzura', 'wzor_numer'):
            if field in data and not isinstance(data[field], str):
                raise ValueError(f'Pole {field} musi być tekstem.')
        year = read_card_integer(data, 'wydanie_rok', 0, 0)
        edition_values = {field: data[field] for field in ('wydanie_numer', 'wydanie_tag')}
        edition_values['wydanie_rok'] = year
        if 'wydanie_naklad' in data:
            edition_values['wydanie_naklad'] = read_card_integer(data, 'wydanie_naklad', 0, None)
        if 'wydanie_cenzura' in data:
            edition_values['wydanie_cenzura'] = data['wydanie_cenzura']
        references = {
            field: read_card_integer(data, field, 1, None)
            for field, _ in reference_fields
        }
    except KeyError as error:
        return jsonify({'error': f'Brak wymaganego pola {error.args[0]}.'}), 400
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            'SELECT wzor_id FROM wydanie WHERE wydanie_id = ?', (wydanie_id,)
        ).fetchone()
        if row is None:
            return jsonify({'error': 'Nie znaleziono karty.'}), 404

        for field, table in reference_fields:
            value = references[field]
            if value is not None and conn.execute(
                f'SELECT 1 FROM {table} WHERE {field} = ?', (value,)
            ).fetchone() is None:
                return jsonify({'error': f'Nie znaleziono wpisu dla pola {field}.'}), 400

        if 'cenzura_id' in references:
            edition_values['cenzura_id'] = references.pop('cenzura_id')
        edition_assignments = ', '.join(f'{column} = ?' for column in edition_values)
        conn.execute(f'UPDATE wydanie SET {edition_assignments} WHERE wydanie_id = ?',
                     (*edition_values.values(), wydanie_id))

        pattern_values = {**references, 'wzor_opis': data['wzor_opis']}
        if 'wzor_numer' in data:
            pattern_values['wzor_numer'] = data['wzor_numer']
        pattern_assignments = ', '.join(f'{column} = ?' for column in pattern_values)
        pattern_update = conn.execute(
            f'UPDATE wzory SET {pattern_assignments} WHERE wzor_id = ?',
            (*pattern_values.values(), row['wzor_id']),
        )
        if pattern_update.rowcount != 1:
            return jsonify({'error': 'Nie znaleziono spójnego wzoru dla wydania.'}), 409
        conn.commit()
        return jsonify({'success': True})
    except sqlite3.Error:
        app.logger.exception('Nie udało się zapisać wydania %s', wydanie_id)
        return jsonify({'error': 'Nie udało się zapisać pocztówki.'}), 500
    finally:
        if conn is not None and conn.in_transaction:
            conn.rollback()

# --- Widoki HTML (Statyczne kontenery) ---


@app.route('/')
def index():
    # Nie przekazujemy już danych, frontend je sobie pobierze
    return render_template('index.html', user=get_user_data())


@app.route('/view/<int:card_id>')
def view_card(card_id):
    # ID jest w URL, frontend wyciągnie je z window.location lub przekażemy je jako prostą zmienną JS
    return render_template('detail.html', card_id=card_id, user=get_user_data())


if __name__ == '__main__':
    if not os.path.exists(IMAGE_FOLDER):
        os.makedirs(IMAGE_FOLDER)
    app.logger.info("Pocztowki aplication starting")
    # app.run(host="0.0.0.0", port=env.get("PORT", 3000), debug=True)
    serve(app, host="0.0.0.0", port=5000)
