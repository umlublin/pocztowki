import sqlite3
from flask import Flask, render_template, request, g

app = Flask(__name__)
DATABASE = 'pocztowki.db'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        # Dzięki temu możemy odwoływać się do kolumn po nazwach
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route('/')
def index():
    query = request.args.get('q', '')
    year_filter = request.args.get('year', '')

    conn = get_db()
    cursor = conn.cursor()

    # Bazowe zapytanie SQL złączeniami (LEFT JOIN), aby pobrać dane powiązane
    sql = """
        SELECT 
            w.id,
            w.wzor_full,
            w.year,
            w.naklad,
            w.tag,
            wz.opis as opis_wzoru,
            m.nazwa as miasto,
            a.imie_nazwisko as autor
        FROM wydanie w
        LEFT JOIN wzory wz ON w.wzor_id = wz.id
        LEFT JOIN miasta m ON wz.city_id = m.id
        LEFT JOIN autorzy a ON wz.author_id = a.id
        WHERE 1=1
    """

    params = []

    # Logika wyszukiwania
    if query:
        # Szukamy w nazwie miasta, opisie wzoru, autorze lub numerze wzoru
        search_term = f"%{query}%"
        sql += """ AND (
            m.nazwa LIKE ? OR 
            wz.opis LIKE ? OR 
            a.imie_nazwisko LIKE ? OR 
            w.wzor_full LIKE ?
        )"""
        params.extend([search_term, search_term, search_term, search_term])

    if year_filter:
        sql += " AND w.year = ?"
        params.append(year_filter)

    sql += " ORDER BY w.id DESC LIMIT 100"

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    return render_template('index.html', pocztowki=rows, search_query=query, year_filter=year_filter)


if __name__ == '__main__':
    app.run(debug=True)