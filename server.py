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

    cursor.execute("SELECT cenzura_id, cenzura_numer FROM cenzura ORDER BY cenzura_numer ASC")
    cenzura = dict_list_from_rows(cursor.fetchall())

    return jsonify({
        'miasta': cities,
        'autorzy': authors,
        'wydawcy': publishers,
        'cenzura': cenzura,
        'tagi': ['panorama', 'kolor', 'ramka', 'lotnicze'],
        'sort': [{'field_id': 'wydanie_rok', 'field_name': "Rok wydania"},
                 {'field_id': 'wzor_numer', 'field_name': 'Numer'},
                 {'field_id': 'miasto_nazwa', 'field_name': 'Miasto'},
                 {'field_id': 'autor_nazwa', 'field_name': 'Autor'},
                 {'field_id': 'wydawca_nazwa', 'field_name': 'Wydawca'}]
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

    #TODO: dodac zabezpieczenie przed SQL injectionm
    if sort_filter:
        sql += f" ORDER BY {sort_filter} LIMIT 10 OFFSET {offset}"

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
