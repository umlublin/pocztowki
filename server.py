from logging.handlers import RotatingFileHandler
import logging
from urllib.parse import quote_plus, urlencode
from authlib.integrations.flask_client import OAuth
import sqlite3
import os
import re
from os import environ as env
from flask import Flask, redirect, render_template, request, g, send_from_directory, abort, jsonify,session
from PIL import Image
from requests.compat import quote_plus
from waitress import serve
from dotenv import find_dotenv, load_dotenv

ENV_FILE = find_dotenv()
if ENV_FILE:
    print("Load .env values from", ENV_FILE)
    load_dotenv(ENV_FILE)

MY_URL = env.get("MY_URL")
DATA_ROOT = env.get("DATA_ROOT", "./")

admins = {sid for sid in (env.get('ADMIN_SID'), env.get('ADMIN_SID_BACKUP')) if sid}

SEARCH_SORT_FIELDS = {
    'wydanie_rok': ('Rok wydania', 'wyd.wydanie_rok'),
    'wzor_numer': ('Numer', 'wz.wzor_numer'),
    'miasto_nazwa': ('Miasto', 'm.miasto_nazwa'),
    'autor_nazwa': ('Autor', 'a.autor_nazwa'),
    'wydawca_nazwa': ('Wydawca', 'pub.wydawca_nazwa'),
}
SQLITE_MAX_INTEGER = 2**63 - 1

file_handler = RotatingFileHandler(env.get("LOG_ROOT", './') + 'pocztowka_app.log', maxBytes=1024000, backupCount=10)
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
THUMB_FOLDER = os.path.join(DATA_ROOT, 'images/thumbnails')
THUMB_SIZE = 120  # Max szerokość/wysokość w pikselach

oauth = OAuth(app)

oauth.register(
    "auth0",
    client_id=env.get("AUTH0_CLIENT_ID"),
    client_secret=env.get("AUTH0_CLIENT_SECRET"),
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f'https://{env.get("AUTH0_DOMAIN")}/.well-known/openid-configuration'
)

def get_user_data():
    userinfo = (session.get('user') or {}).get('userinfo') or {}
    if not userinfo:
        return {}
    return {**userinfo, 'is_admin': userinfo.get('sub') in admins}

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
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
    return oauth.auth0.authorize_redirect(
        redirect_uri=f'{env.get("MY_URL")}callback'
    )


@app.route("/callback", methods=["GET", "POST"])
def callback():
    token = oauth.auth0.authorize_access_token()
    session["user"] = token
    return redirect("/")        

@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        "https://" + env.get("AUTH0_DOMAIN")
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": f'{env.get("MY_URL")}',
                "client_id": env.get("AUTH0_CLIENT_ID"),
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


def ensure_thumb_folder():
    if not os.path.exists(THUMB_FOLDER):
        os.makedirs(THUMB_FOLDER)

@app.route('/icons/<path:path>')
def send_icons(path):
    return send_from_directory(DATA_ROOT + 'icons', path)

@app.route('/images/<int:img_id>.jpg')
def serve_original_image(img_id):
    """Serwuje pełny obrazek"""
    return send_from_directory(IMAGE_FOLDER, f"{img_id}.jpg")


@app.route('/images/<int:img_id>_mini.jpg')
def serve_thumbnail(img_id):
    """Generuje, cachuje i serwuje miniaturkę"""
    ensure_thumb_folder()

    thumb_filename = f"{img_id}_mini.jpg"
    thumb_path = os.path.join(THUMB_FOLDER, thumb_filename)
    original_path = os.path.join(IMAGE_FOLDER, f"{img_id}.jpg")

    # 1. Sprawdź czy miniaturka już istnieje (cache na dysku)
    if os.path.exists(thumb_path):
        return send_from_directory(THUMB_FOLDER, thumb_filename)

    # 2. Jeśli nie ma miniaturki, sprawdź czy jest oryginał
    if not os.path.exists(original_path):
        return abort(404)  # Brak zdjęcia

    # 3. Generuj miniaturkę
    try:
        with Image.open(original_path) as img:
            # Konwertuj na RGB (na wypadek PNG/RGBA) przed zapisem jako JPG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.thumbnail((THUMB_SIZE, THUMB_SIZE))  # Zachowuje proporcje
            img.save(thumb_path, "JPEG", quality=85)

        return send_from_directory(THUMB_FOLDER, thumb_filename)
    except Exception as e:
        print(f"Błąd generowania miniatury: {e}")
        return abort(500)

    # --- API Endpoints (JSON) ---


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


@app.route('/api/search')
def api_search():
    """Zwraca listę pocztówek wg filtrów"""
    query = request.args.get('q', '')
    rok_filter = request.args.get('rok', type=int)
    miasto_filter = request.args.get('miasto_id', type=int)
    autor_filter = request.args.get('autor_id', type=int)
    wydawca_filter = request.args.get('wydawca_id', type=int)
    wzor_numer = request.args.get('wzor_numer', type=str)
    sort_filter = request.args.get('sort', type=str, default='wydanie_rok')
    offset = request.args.get('offset', type=int, default=0)
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
                 concat(wz.wydawca_id, '-', wz.wzor_numer) as wydawca_wzor_numer, \
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

    if rok_filter:
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
        sql += " AND wzor_numer = ?"
        params.append(wzor_numer)

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
          SELECT wyd.*, \
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

    try:
        for field in text_fields:
            if not isinstance(data.get(field), str):
                raise ValueError(f'Pole {field} jest wymagane i musi być tekstem.')
        year = read_card_integer(data, 'wydanie_rok', 0, 0)
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

        conn.execute(
            """UPDATE wydanie SET wydanie_numer = ?, wydanie_rok = ?, wydanie_tag = ?
               WHERE wydanie_id = ?""",
            (data['wydanie_numer'], year, data['wydanie_tag'], wydanie_id),
        )
        pattern_update = conn.execute(
            """UPDATE wzory SET miasto_id = ?, wzor_opis = ?, autor_id = ?, wydawca_id = ?
               WHERE wzor_id = ?""",
            (references['miasto_id'], data['wzor_opis'], references['autor_id'],
             references['wydawca_id'], row['wzor_id']),
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
    return render_template('index.html')


@app.route('/view/<int:card_id>')
def view_card(card_id):
    # ID jest w URL, frontend wyciągnie je z window.location lub przekażemy je jako prostą zmienną JS
    return render_template('detail.html', card_id=card_id)


if __name__ == '__main__':
    if not os.path.exists(IMAGE_FOLDER):
        os.makedirs(IMAGE_FOLDER)
    app.logger.info("Pocztowki aplication starting")
    # app.run(host="0.0.0.0", port=env.get("PORT", 3000), debug=True)
    serve(app, host="0.0.0.0", port=5000)
