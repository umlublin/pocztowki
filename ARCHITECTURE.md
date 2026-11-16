# Architektura aplikacji Pocztówki

Przegląd obejmuje wszystkie pliki śledzone w rewizji [`40d50b1`](https://github.com/umlublin/pocztowki/tree/40d50b1c8d72650607f62f6d75b118f676e87714). Opis opiera się na analizie statycznej kodu i konfiguracji. Baza, skany i konfiguracja Auth0 są poza repozytorium, więc działania wdrożenia nie weryfikowano.

## Co robi aplikacja

To publiczny katalog wydań pocztówek. Lista pokazuje metadane i miniatury awersów, pozwala szukać po opisie i numerze wzoru, filtrować po mieście, fotografie i wydawcy oraz sortować i doładowywać wyniki. Szczegóły pokazują metadane i dostępne skany obu stron z powiększeniem. Po zalogowaniu można zapisać edycję wybranych pól wydania i wzoru.

## Przepływ danych

| Element | Odpowiedzialność |
| --- | --- |
| [`templates/index.html`](templates/index.html) | Strona `/` pobiera `GET /api/filters` i `GET /api/search`. Standardowa porcja wyników to 10 wydań. |
| [`templates/detail.html`](templates/detail.html) | Strona `/view/<id>` pobiera `GET /api/card/<id>` i zapisuje zmiany przez `PUT /api/card/<id>`. |
| [`server.py`](server.py) | Jeden moduł Flask zawiera routing, zapytania SQL, sesje i obsługę obrazów. SQLite jest otwierane w kontekście żądania i zamykane przy jego zakończeniu. |
| SQLite | `DATA_ROOT/instance/pocztowki.db`. Tabela `wydanie` wskazuje `wzory`, a zapytania korzystają też ze słowników `miasta`, `autorzy`, `wydawcy` i `cenzura`. Zapis wydania i wzoru odbywa się w jednej transakcji. Zmiana wzoru dotyczy wszystkich powiązanych wydań. |
| Obrazy | `awers_id` i `rewers_id` wskazują `DATA_ROOT/images/<id>.jpg`. Pillow na żądanie tworzy miniaturę JPEG do 120 × 120 px z zachowaniem proporcji i zapisuje ją w `images/thumbnails/`. |
| Logowanie | Trasy `/login`, `/callback` i `/logout` obsługują Auth0. API edycji sprawdza obecność zalogowanej sesji. Flaga `is_admin` jest wyliczana w danych użytkownika. |

## Zależności i uruchomienie

- [`requirements.txt`](requirements.txt) deklaruje Flask ≥ 2.0.3, python-dotenv ≥ 0.19.2, Authlib ≥ 1.0, requests ≥ 2.27.1, Flask-SQLAlchemy ≥ 2.5.1, Alembic, Waitress i Pillow. Flask-SQLAlchemy i Alembic nie są używane przez aplikację. Warstwa danych korzysta z modułu `sqlite3` Pythona, a wyszukiwarka wymaga dostępności funkcji SQL `concat()`.
- Interfejs używa Jinja dostarczanej przez Flask, HTML, CSS i zwykłego JavaScriptu. Dwie ikony PNG znajdują się w [`icons/`](icons/). Frontend nie ma osobnego procesu budowania.
- [`install-deps.sh`](install-deps.sh) tworzy `.venv`. [`run.sh`](run.sh) i [`pocztowki.service`](pocztowki.service) zakładają instalację w `/home/pocztowki` i uruchamiają `server.py`, który startuje Waitress na porcie 5000. `install-service.sh` kopiuje jednostkę systemd, a `start.sh`, `stop.sh` i `restart.sh` sterują usługą. [`nginx.site.example`](nginx.site.example) pokazuje reverse proxy i TLS.
- Ustawienia pochodzą ze środowiska lub `.env`. [`.gitignore`](.gitignore) wyłącza bazę, skany, konfigurację lokalną, log i pliki tymczasowe. [`README.md`](README.md) wskazuje demo, a [`LICENSE`](LICENSE) zawiera licencję Apache 2.0. [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) opisuje szczegóły konfiguracji oraz trasy.

Opcja dodawania wpisów słownikowych jest szkieletem. Przyciski poprzedniego i następnego wydania zależą od pól, których backend sam nie wylicza. Tworzenie i usuwanie wydań, import i przesyłanie skanów wykraczają poza aktualny zakres aplikacji. Błędy i otwarte decyzje są opisane w [`TODO.md`](TODO.md).
