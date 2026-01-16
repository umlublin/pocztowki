import sqlite3
import os
from flask import Flask, render_template, request, g, send_from_directory, abort, jsonify
from PIL import Image

app = Flask(__name__)
DATABASE = './instance/pocztowki.db'
IMAGE_FOLDER = './images'
THUMB_FOLDER = './images/thumbnails'
THUMB_SIZE = 120  # Max szerokość/wysokość w pikselach


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# Helper do konwersji wierszy DB na dict (dla JSON)
def dict_from_row(row):
    return dict(zip(row.keys(), row))


def dict_list_from_rows(rows):
    return [dict_from_row(r) for r in rows]


def ensure_thumb_folder():
    if not os.path.exists(THUMB_FOLDER):
        os.makedirs(THUMB_FOLDER)


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

    return jsonify({
        'miasta': cities,
        'autorzy': authors,
        'wydawcy': publishers,
        'tagi': ['pano', 'kolor', 'ramka']
    })


@app.route('/api/search')
def api_search():
    """Zwraca listę pocztówek wg filtrów"""
    query = request.args.get('q', '')
    rok_filter = request.args.get('rok', type=int)
    miasto_filter = request.args.get('miasto_id', type=int)
    autor_filter = request.args.get('autor_id', type=int)
    wydawca_filter = request.args.get('wydawca_id', type=int)
    wzor_numer = request.args.get('wzor_numer', type=int)

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
                 concat(wz.wydawca_id, '-', wz.wzor_numer) as wzor_id, \
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
        sql += " AND wz.wzor_numer = ?"
        params.append(wzor_numer)

    sql += " ORDER BY wyd.wydanie_id DESC LIMIT 100"

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    return jsonify(dict_list_from_rows(rows))


@app.route('/api/card/<int:card_id>')
def api_card_detail(card_id):
    conn = get_db()
    cursor = conn.cursor()

    sql = """
          SELECT w.*, \
                 wz.opis         as opis_wzoru, \
                 wz.wydawca_id, \
                 wz.numer_wzoru, \
                 m.name          as miasto, \
                 m.aliases       as miasto_alias, \
                 a.id            as author_id, \
                 a.imie_nazwisko as autor, \
                 a.lata          as autor_lata, \
                 a.url           as autor_url, \
                 c.oznaczenie    as cenzura, \
                 w.cenzor_full as cenzor_full, \
                 wyd.name        as wydawca
          FROM wydanie w
                   LEFT JOIN wzory wz ON w.wzor_id = wz.id
                   LEFT JOIN miasta m ON wz.city_id = m.id
                   LEFT JOIN autorzy a ON wz.author_id = a.id
                   LEFT JOIN cenzura c ON w.cenzor_id = c.id
                   LEFT JOIN wydawcy wyd ON wz.wydawca_id = wyd.id
          WHERE w.id = ? \
          """
    cursor.execute(sql, (card_id,))
    row = cursor.fetchone()

    if row is None:
        return jsonify({'error': 'Pocztówka nie istnieje'}), 404

    return jsonify(dict_from_row(row))


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
    app.run(debug=False)
