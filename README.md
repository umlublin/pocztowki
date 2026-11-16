# Repozytorium pocztówek

[Demo](https://pocztowki.online/)

## Uruchomienie lokalne

Z katalogu repozytorium, na Pythonie 3.10 lub nowszym:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
DEMO_ROOT="$(mktemp -d)/pocztowki"
.venv/bin/python demo_data.py "$DEMO_ROOT"
DATA_ROOT="$DEMO_ROOT" .venv/bin/python server.py
```

Katalog będzie dostępny pod `http://localhost:5000`. Skrypt tworzy przykładową bazę z 12 wydaniami i dwoma obrazami JPEG w nowym katalogu. Do publicznego przeglądania nie trzeba konfigurować Auth0. Aplikacja korzysta z modułu `sqlite3` dostarczanego z Pythonem i nie wymaga funkcji `concat()` dostępnej dopiero w nowszych wydaniach SQLite. Wersję biblioteki można odczytać przez `.venv/bin/python -c "import sqlite3; print(sqlite3.sqlite_version)"`.

| Ustawienie środowiska lub `.env` | Zastosowanie |
| --- | --- |
| `DATA_ROOT` | Katalog zawierający `instance/pocztowki.db` oraz `images/`. Domyślnie bieżący katalog roboczy. |
| `LOG_ROOT` | Istniejący katalog na log aplikacji, domyślnie bieżący katalog roboczy. |
| `MY_URL` | Bazowy URL, np. `http://localhost:5000`. Zarejestruj w Auth0 adres powrotu `http://localhost:5000/callback` i adres po wylogowaniu `http://localhost:5000/`. |
| `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `APP_SECRET_KEY` | Konfiguracja Auth0 oraz sekret sesji Flask. `AUTH0_DOMAIN` to nazwa hosta bez protokołu. |
| `ADMIN_SID`, `ADMIN_SID_BACKUP` | Identyfikatory `sub` użytkowników dopuszczonych do edycji. |

Miniatury w `images/thumbnails/` są odtwarzalne. Aplikacja używa osobnej wersji miniatury po zmianie pliku źródłowego. Starsze wersje można usunąć podczas postoju aplikacji.

## Testy

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Testy tworzą osobny katalog tymczasowy i obejmują stronicowanie, filtry, sąsiadów wydania, uprawnienia, transakcję edycji oraz tworzenie i odświeżanie miniatur. Sesje są ustawiane przez klienta testowego Flask.

## Zakres katalogowania

Administrator może edytować istniejące wydanie i jego wzór, w tym nakład, tekstowe oznaczenie cenzury, numer cenzury ze słownika i numer wzoru. Zmiana numeru wzoru obejmuje wszystkie jego wydania. Przyciski „Dodaj miasto”, „Dodaj autora” i „Dodaj wydawcę” zapisują wpis słownikowy od razu i wybierają go w formularzu. Przypisanie do wzoru następuje po zapisaniu pocztówki. Nazwy różniące się tylko wielkością liter zwracają istniejący wpis. Słowniki muszą mieć identyfikatory generowane przy zapisie, jak w schemacie demonstracyjnym.

Lista pozwala filtrować po roku, numerze cenzury i pełnej nazwie tagu. Wielkość liter w tagu nie ma znaczenia.

Tworzenie i usuwanie wydań lub wzorów, import i wymiana skanów są poza bieżącym zakresem. Do zaprojektowania tych operacji potrzebny jest schemat używanej bazy oraz ustalenie, kiedy wzór lub skan mogą być współdzielone i usuwane. Dane demonstracyjne dostarczają przykładowy schemat do lokalnego uruchomienia i testów.
