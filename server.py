import sqlite3
import os
from flask import Flask, render_template, request, g, send_from_directory

app = Flask(__name__)
DATABASE = 'pocztowki.db'
IMAGE_FOLDER = './images'  # Ścieżka do folderu z obrazkami


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


# --- Endpoint do serwowania obrazków z lokalnego folderu ---
@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(IMAGE_FOLDER, filename)


@app.route('/')
def index():
    # Pobieranie parametrów z URL
    query = request.args.get('q', '')
    year_filter = request.args.get('year', '')
    city_filter = request.args.get('city_id', type=int)
    author_filter = request.args.get('author_id', type=int)

    conn = get_db()
    cursor = conn.cursor()

    # 1. Pobieranie list do filtrów (dropdownów)
    cursor.execute("SELECT id, name FROM miasta ORDER BY name ASC")
    all_cities = cursor.fetchall()

    cursor.execute("SELECT id, imie_nazwisko FROM autorzy ORDER BY imie_nazwisko ASC")
    all_authors = cursor.fetchall()

    # 2. Główne zapytanie wyszukujące
    sql = """
          SELECT w.id, \
                 w.wzor_full, \
                 w.year, \
                 w.naklad, \
                 w.tag, \
                 w.awers_id, \
                 w.revers_id, \
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

    # Logika filtrów
    if query:
        search_term = f"%{query}%"
        sql += """ AND (
            wz.opis LIKE ? OR 
            w.wzor_full LIKE ? OR
            w.tag LIKE ?
        )"""
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

    return render_template(
        'index.html',
        pocztowki=rows,

        # Przekazujemy dane formularza z powrotem, aby utrzymać stan
        search_query=query,
        year_filter=year_filter,
        city_filter=city_filter,
        author_filter=author_filter,

        # Przekazujemy listy do dropdownów
        all_cities=all_cities,
        all_authors=all_authors
    )


if __name__ == '__main__':
    # Upewnij się, że folder images istnieje, żeby nie było błędu przy starcie
    if not os.path.exists(IMAGE_FOLDER):
        os.makedirs(IMAGE_FOLDER)
        print(f"Utworzono folder: {IMAGE_FOLDER} - wrzuć tam pliki .jpg")

    app.run(debug=True)