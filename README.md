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

## Eksport schematu aktualnej bazy

Z katalogu repozytorium uruchom na maszynie mającej dostęp do właściwej bazy:

```sh
python3 export_schema.py /sciezka/do/instance/pocztowki.db schema.sql
```

Skrypt otwiera bazę wyłącznie do odczytu. Zapisuje definicje tabel (z kolumnami
i ograniczeniami), indeksów, widoków i wyzwalaczy; pomija rekordy i wewnętrzne
obiekty `sqlite_*`. Nie nadpisuje istniejącego pliku wyjściowego.
Definicje SQL mogą zawierać komentarze i wartości domyślne — sprawdź plik przed
udostępnieniem. Udostępnij wygenerowany `schema.sql` w czacie lub dodaj go do
repozytorium, aby można było sprawdzić rzeczywisty schemat, w tym pole `aliases`.
Eksport bazy demonstracyjnej opisuje tylko bazę demonstracyjną.

## Testy automatyczne

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Testy tworzą osobny katalog tymczasowy i obejmują stronicowanie, filtry, sąsiadów wydania, uprawnienia, transakcję edycji oraz tworzenie i odświeżanie miniatur. Sesje są ustawiane przez klienta testowego Flask.

## Zakres katalogowania

### Fotografowie

Odnośnik „Fotografowie” w nawigacji prowadzi do publicznej listy `/photographers`,
z wyszukiwaniem po nazwisku lub aliasie. Nazwisko prowadzi do pocztówek fotografa.
Administrator może edytować imię i nazwisko (`autor_nazwa`), nazwę widoczną na
pocztówce (`alias`), daty urodzenia i śmierci (`autor_lata`, tekst pozwalający także
na daty niepełne) oraz internetowy link do biogramu (`autor_url`, HTTP/HTTPS).
Pola poza imieniem i nazwiskiem są opcjonalne. Zmiana dotyczy istniejącego rekordu
w tabeli `autorzy`, więc zachowuje powiązania z pocztówkami.

Nowe dane demonstracyjne zawierają już kolumnę `alias`. Dla istniejącej bazy
zatrzymaj aplikację, wykonaj kopię zapasową pliku bazy i uruchom jednorazowo:

```sh
.venv/bin/python migrate_authors.py /sciezka/do/instance/pocztowki.db
```

Migracja dodaje brakującą kolumnę `alias TEXT` bez zmiany istniejących rekordów.
Można ją bezpiecznie powtórzyć. Wykonaj ją przed wejściem na nową listę fotografów.

### Miejscowości

Odnośnik „Miejscowości” prowadzi do publicznej listy `/towns` z wyszukiwaniem po
nazwie (bez rozróżniania wielkości liter). Nazwa prowadzi do pocztówek wybranej
miejscowości. Administrator może zmienić `miasto_nazwa` w tabeli `miasta`.
Zapis zachowuje identyfikator i powiązania z wzorami oraz odrzuca pustą nazwę,
nazwę dłuższą niż 200 znaków i duplikat nazwy innej miejscowości.
Nie jest wymagana migracja bazy danych.

### Pocztówki

Administrator może edytować istniejące wydanie i jego wzór, w tym nakład, tekstowe oznaczenie cenzury, numer cenzury ze słownika i numer wzoru. Zmiana numeru wzoru obejmuje wszystkie jego wydania. Przyciski „Dodaj miasto”, „Dodaj autora” i „Dodaj wydawcę” zapisują wpis słownikowy od razu i wybierają go w formularzu. Przypisanie do wzoru następuje po zapisaniu pocztówki. Nazwy różniące się tylko wielkością liter zwracają istniejący wpis. Słowniki muszą mieć identyfikatory generowane przy zapisie, jak w schemacie demonstracyjnym.

Lista pozwala filtrować po roku, numerze cenzury i pełnej nazwie tagu. Wielkość liter w tagu nie ma znaczenia.

Tworzenie i usuwanie wydań lub wzorów, import i wymiana skanów są poza bieżącym zakresem. Do zaprojektowania tych operacji potrzebny jest schemat używanej bazy oraz ustalenie, kiedy wzór lub skan mogą być współdzielone i usuwane. Dane demonstracyjne dostarczają przykładowy schemat do lokalnego uruchomienia i testów.
