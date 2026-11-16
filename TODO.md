# TODO aplikacji Pocztówki

Lista wynika z przeglądu kodu w rewizji [`40d50b1`](https://github.com/umlublin/pocztowki/tree/40d50b1c8d72650607f62f6d75b118f676e87714). Priorytety są propozycją na podstawie wpływu na dane i podstawowe funkcje katalogu.

## P0 — Bezpieczeństwo i zapis danych

- [x] Sortowanie korzysta z listy dozwolonych kolumn i parametryzowanego przesunięcia.
- [x] Szablony wstawiają dynamiczne treści przez DOM. Zewnętrzny odnośnik autora akceptuje HTTP i HTTPS.
- [x] Edycja jest dostępna dla administratorów z `ADMIN_SID` i `ADMIN_SID_BACKUP`. Formularz informuje o wpływie zmiany wzoru na inne wydania.
- [x] API sprawdza pola i identyfikatory słowników oraz zwraca ogólny komunikat przy błędzie zapisu.

## P1 — Błędy i nieukończone ścieżki

- [x] Lista odtwarza filtry URL po pobraniu słowników. Reset czyści również filtry przekazane linkiem ze szczegółów.
- [x] Stronicowanie używa stałego rozmiaru porcji i kolejności z rozstrzyganiem remisów. Zmiana filtrów przerywa poprzednie pobieranie.
- [x] Sąsiedzi są wyznaczani według identyfikatora wydania. Odtworzenie z historii nie dopisuje wpisu.
- [x] Oba widoki używają wspólnego nagłówka sesji. Ikony są zasobami aplikacji, a adres powrotu Auth0 jest normalizowany.
- [x] Miniatury są zapisywane atomowo i wersjonowane według pliku źródłowego. Widoki pokazują informację o braku skanu.
- [x] Instrukcja lokalnego uruchomienia, generator danych demonstracyjnych i testy integracyjne znajdują się w repozytorium. Usunięto nieużywane zależności ORM i migracji.

## P2 — Brakujące funkcje

- [x] Administrator może dodać miasto, autora lub wydawcę z formularza edycji.
- [x] Ustalono zakres katalogowania. Obecna aplikacja edytuje istniejące wydania i wzory oraz uzupełnia słowniki. Zasady dalszej rozbudowy opisuje [README.md](README.md#zakres-katalogowania).
- [x] Lista filtruje po roku, tagu i numerze cenzury. Formularz edytuje nakład, oznaczenie i numer cenzury oraz numer wzoru.

## Dalszy rozwój katalogu

- [ ] Pozyskać schemat bazy produkcyjnej i ustalić zasady współdzielenia wzorów i skanów przed wdrożeniem tworzenia i usuwania rekordów, importu oraz dodawania lub wymiany skanów.
