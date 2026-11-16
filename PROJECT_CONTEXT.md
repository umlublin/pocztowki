# Kontekst projektu Pocztówki

Repozytorium: [umlublin/pocztowki](https://github.com/umlublin/pocztowki). Przegląd z 16.11.2026 obejmuje pełne drzewo jedynej widocznej gałęzi `master` w rewizji [`efe3df5`](https://github.com/umlublin/pocztowki/tree/efe3df5e88eac08180a8a1f091646d557b74effe). Stan funkcji wynika z analizy statycznej. Uruchomienie aplikacji, zgodność z rzeczywistą bazą i zachowanie wdrożenia nie były weryfikowane.

## Zastosowane technologie

| Obszar | Implementacja |
| --- | --- |
| Serwer | Python 3 i Flask (`>=2.0.3`), jeden moduł `server.py`. Waitress uruchamia aplikację na porcie 5000. |
| Interfejs | Szablony HTML renderowane przez Flask/Jinja, osadzony CSS i zwykły JavaScript. Widoki pobierają dane przez `fetch` z API JSON. Brak procesu budowania frontendu. |
| Baza | SQLite przez standardowy moduł `sqlite3` i ręcznie pisany SQL. Połączenie utrzymywane w kontekście Flask i zamykane po jego zakończeniu. `flask_sqlalchemy` i `alembic` są w zależnościach, lecz kod ich nie używa. |
| Obrazy | Oryginały na dysku i miniatury generowane przez Pillow na żądanie. |
| Logowanie | Auth0 przez OpenID Connect i Authlib, sesja Flask. |
| Konfiguracja i wdrożenie | Zmienne środowiskowe lub `.env` przez python-dotenv. Repozytorium zawiera jednostkę systemd i przykład reverse proxy Nginx z HTTPS. |

## Struktura katalogów

| Ścieżka | Zawartość |
| --- | --- |
| `server.py` | Trasy HTML i API, zapytania SQLite, logowanie, edycja i obsługa plików obrazów. |
| `templates/index.html` | Lista, formularz wyszukiwania, sortowanie i doładowywanie wyników. |
| `templates/detail.html` | Szczegóły wydania, awers i rewers, powiększenie obrazów oraz formularz edycji. |
| `icons/` | Dwie ikony PNG do logowania i wylogowania. |
| `requirements.txt`, `install-deps.sh` | Zależności i utworzenie środowiska `.venv`. |
| `run.sh`, `install-service.sh`, `start.sh`, `stop.sh`, `restart.sh` | Uruchamianie aplikacji, instalacja jednostki i sterowanie usługą. Ścieżki w `run.sh` i jednostce zakładają katalog `/home/pocztowki`. |
| `pocztowki.service`, `nginx.site.example` | Konfiguracja systemd i przykład konfiguracji Nginx. |
| `README.md`, `LICENSE`, `.gitignore` | Odnośnik do wdrożenia demonstracyjnego, licencja Apache 2.0 i reguły ignorowania danych roboczych. |

## Dane i obrazy

- Domyślny `DATA_ROOT` to `./`. Plik bazy to `DATA_ROOT/instance/pocztowki.db`. Baza, obrazy i `.env` nie są śledzone w Git. Repozytorium nie zawiera DDL, migracji ani danych startowych. Do uruchomienia katalogu potrzebna jest istniejąca baza ze zgodnym schematem. Wyszukiwanie używa funkcji SQLite `concat()`, więc środowisko musi ją udostępniać.
- SQL identyfikuje dwa główne byty. `wydanie` opisuje konkretne wydanie i przez `wzor_id` wskazuje wspólny rekord w `wzory`. Wzór odwołuje się do słowników `miasta`, `autorzy` i `wydawcy`. Szczegóły wydania łączą też `wydanie.cenzura_id` ze słownikiem `cenzura`. Tagi wydania są przechowywane jako tekst rozdzielany przecinkami.
- `awers_id` i `rewers_id` wskazują pliki `DATA_ROOT/images/<id>.jpg`. Lista prosi o `/images/<id>_mini.jpg` dla awersu, a szczegóły używają oryginałów. Przy pierwszym żądaniu Pillow tworzy JPEG o jakości 85, mieszczący się w 120 × 120 px z zachowaniem proporcji. Kolejne żądania korzystają z kopii w `DATA_ROOT/images/thumbnails/`. Brak oryginału przy pustej pamięci podręcznej daje 404. Podmiana oryginału nie odświeża istniejącej miniatury automatycznie.
- Poza `DATA_ROOT` konfiguracja obejmuje `LOG_ROOT`, `MY_URL`, `APP_SECRET_KEY`, `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `ADMIN_SID` i `ADMIN_SID_BACKUP`. `MY_URL` służy do złożenia adresu powrotu Auth0 i kod dokleja do niego `callback` bez dodawania ukośnika. Trasa ikon składa ścieżkę przez `DATA_ROOT + 'icons'`, więc przy zewnętrznym katalogu danych musi się zgadzać separator oraz lokalizacja ikon.

## Funkcje zaimplementowane

| Funkcja | Jak przebiega |
| --- | --- |
| Publiczna lista i wyszukiwanie | `/` pobiera słowniki z `GET /api/filters` oraz wydania z `GET /api/search`. Szukanie tekstowe obejmuje opis i numer wzoru. Formularz pozwala filtrować po mieście, fotografie i wydawcy oraz wybrać sortowanie. Przewijanie pobiera kolejne porcje po 10 rekordów przez `offset`. |
| Szczegóły wydania | `/view/<id>` pobiera `GET /api/card/<id>` i pokazuje metadane oraz dostępne skany awersu i rewersu. Obraz można powiększyć kliknięciem lub klawiszem A/R. Brak wydania daje 404 w API. |
| Sesja użytkownika | `/login`, `/callback` i `/logout` realizują przepływ Auth0, a `GET /api/userdata.json` udostępnia dane sesji interfejsowi szczegółów. Integracja wymaga skonfigurowanego Auth0. |
| Edycja istniejącego wydania i wzoru | Formularz szczegółów wysyła `PUT /api/card/<id>`. Numer wydania, rok i tagi trafiają do `wydanie`. Miasto, opis, autor i wydawca trafiają do `wzory`. Oba zapisy są zatwierdzane razem. Zmiana wzoru wpływa na wszystkie jego wydania. Do zapisu wystarcza zalogowana sesja, a anonimowe wywołanie otrzymuje 403. |

## Szkielety, niepełne połączenia i braki

- **Dodawanie do słowników.** W selektorach miasta, autora i wydawcy jest opcja „Dodaj nowy”. Jej wybranie blokuje zapis z komunikatem o braku implementacji. Nie ma tras tworzących wpisy słownikowe.
- **Nawigacja między wydaniami.** Przyciski poprzednie/następne i strzałki są w szablonie. Oczekują `prev_id` i `next_id`, których backend sam nie wylicza. Jeżeli tych kolumn nie ma w `wydanie` (szczegóły pobierają `wyd.*`), przyciski pozostają wyłączone. Schemat bazy jest poza repozytorium.
- **Filtry i odnośniki.** API wyszukiwania obsługuje również `rok` i `wzor_numer`, których nie ma w formularzu listy. Link numeru wzoru ze szczegółów przekazuje `wzor_numer`, ale lista go nie przenosi do żądania. Linki z parametrami miasta, autora lub wydawcy też mogą zostać pominięte, ponieważ formularz ma już dla tych pól wartość `0`. API słowników zwraca cenzurę i zestaw tagów. Tagi są używane w edycji, a katalog nie ma filtrów tagów ani cenzury.
- **Uprawnienia w interfejsie.** Backend oblicza `is_admin`, ale zapis go nie sprawdza. Przycisk edycji jest również dostępny anonimowo, choć API odrzuca zapis. Nagłówek listy ma kontener informacji o sesji, lecz wypełnia go tylko kod widoku szczegółów.
- **Zakres katalogowania.** Brak tworzenia i usuwania wydań lub wzorów, importu oraz przesyłania, podmiany i usuwania obrazów przez aplikację. Numer wzoru, nakład, cenzura, zamówienie i identyfikatory skanów są poza zakresem formularza edycji.
- **Walidacja.** Wyszukiwarka wstawia parametr sortowania z żądania do SQL bez sprawdzenia go z listą dozwolonych kolumn. Szablony w kilku miejscach interpolują dane do `innerHTML` bez jawnego kodowania. W repozytorium nie ma testów automatycznych ani konfiguracji CI.

## Punkty wejścia do kolejnych zmian

- Zmiany wyszukiwania wymagają sprawdzenia razem `api_filters()`, `api_search()` i `templates/index.html`.
- Zmiany formularza wymagają sprawdzenia `api_card_detail()`, `api_card_update()` i `templates/detail.html`. Przed zmianą modelu danych trzeba pozyskać schemat używanej bazy.
- Zmiany skanów i miniaturek dotyczą tras `serve_original_image()` i `serve_thumbnail()` oraz adresów używanych przez oba widoki.
