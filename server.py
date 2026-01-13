import sqlite3
import os
from flask import Flask, render_template, request, g, send_from_directory, abort
from PIL import Image

app = Flask(__name__)
DATABASE = 'pocztowki.db'
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


# --- Funkcje pomocnicze do obrazków ---

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


# --- Widoki Aplikacji ---

@app.route('/')
def index():
    query = request.args.get('q', '')
    year_filter = request.args.get('year', '')
    city_filter = request.args.get('city_id', type=int)
    author_filter = request.args.get('author_id', type=int)

    conn = get_db()
    cursor = conn.cursor()

    # Listy do filtrów
    cursor.execute("SELECT id, name FROM miasta ORDER BY name ASC")
    all_cities = cursor.fetchall()
    cursor.execute("SELECT id, imie_nazwisko FROM autorzy ORDER BY imie_nazwisko ASC")
    all_authors = cursor.fetchall()

    sql = """
          SELECT w.id, \
                 w.wzor_full, \
                 w.year, \
                 w.naklad, \
                 w.tag, \
                 w.awers_id, \
                 wz.opis         as opis_wzoru, \
                 m.name          as miasto, \
                 a.imie_nazwisko as autor
          FROM wydanie w
                   LEFT JOIN wzory wz ON w.wzor_id = wz.id
                   LEFT JOIN miasta m ON wz.city_id = m.id
                   LEFT JOIN autorzy a ON wz.author_id = a.id
          WHERE 1 = 1 \
          """

    params = []

    if query:
        search_term = f"%{query}%"
        sql += " AND (wz.opis LIKE ? OR w.wzor_full LIKE ? OR w.tag LIKE ?)"
        params.extend([search_term, search_term, search_term])

    if year_filter:
        sql += " AND w.year = ?"
        params.append(year_filter)
    if city_filter:
        sql += " AND wz.city_id = ?"
        params.append(city_filter)
    if author_filter:
        sql += " AND wz.author_id = ?"
        params.append(author_filter)

    sql += " ORDER BY w.id DESC LIMIT 100"

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    return render_template('index.html', pocztowki=rows,
                           search_query=query, year_filter=year_filter,
                           city_filter=city_filter, author_filter=author_filter,
                           all_cities=all_cities, all_authors=all_authors)


@app.route('/view/<int:card_id>')
def view_card(card_id):
    conn = get_db()
    cursor = conn.cursor()

    # Pobieramy szczegóły jednej pocztówki
    sql = """
          SELECT w.*, \
                 wz.opis         as opis_wzoru, \
                 wz.numer_wydawcy, \
                 wz.numer_wzoru, \
                 m.name          as miasto, \
                 m.aliases       as miasto_alias, \
                 a.imie_nazwisko as autor, \
                 a.url           as autor_url, \
                 c.oznaczenie    as cenzura, \
                 wyd.name        as wydawca
          FROM wydanie w
                   LEFT JOIN wzory wz ON w.wzor_id = wz.id
                   LEFT JOIN miasta m ON wz.city_id = m.id
                   LEFT JOIN autorzy a ON wz.author_id = a.id
                   LEFT JOIN cenzura c ON w.cenzor_id = c.id
                   LEFT JOIN wydawcy wyd ON wz.numer_wydawcy = wyd.id
          WHERE w.id = ? \
          """
    cursor.execute(sql, (card_id,))
    row = cursor.fetchone()

    if row is None:
        return "Pocztówka nie istnieje", 404

    return render_template('detail.html', p=row)


if __name__ == '__main__':
    if not os.path.exists(IMAGE_FOLDER):
        os.makedirs(IMAGE_FOLDER)
    app.run(debug=True)