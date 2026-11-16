# TODO aplikacji Pocztówki

Lista wynika z przeglądu kodu w rewizji [`40d50b1`](https://github.com/umlublin/pocztowki/tree/40d50b1c8d72650607f62f6d75b118f676e87714). Priorytety są propozycją na podstawie wpływu na dane i podstawowe funkcje katalogu.

## P0 — Bezpieczeństwo i zapis danych

- [ ] **Walidować sortowanie w `api_search()`.** Parametr `sort` trafia bezpośrednio do `ORDER BY`. Mapować wartości z API na stałe kolumny SQL, ustalić domyślne sortowanie i parametryzować lub walidować przesunięcie.
- [ ] **Bezpiecznie renderować metadane i dane użytkownika.** Oba szablony wstawiają część danych do HTML. Budować elementy DOM i używać `textContent` dla treści, a dla odnośników z bazy walidować dozwolone schematy URL.
- [ ] **Ustalić i egzekwować uprawnienia edycji.** Dziś zapisać może każdy zalogowany użytkownik. Ustalić dopuszczone role, egzekwować je w `PUT /api/card/<id>` i pokazywać edycję zgodnie z tym samym warunkiem. Formularz powinien też sygnalizować wpływ zmiany wzoru na inne wydania.
- [ ] **Walidować żądania aktualizacji.** Niepoprawne wartości są zamieniane na `NULL` lub 0, a brakujące pola tekstowe na puste ciągi. Zdefiniować wymagane pola, obsługę pustych wartości i walidację identyfikatorów słowników. Zwracać czytelne błędy bez szczegółów wyjątków serwera.

## P1 — Błędy i nieukończone ścieżki

- [ ] **Naprawić parametry listy i reset.** Wartość `0` w selektorach blokuje przejęcie filtrów z URL, a `wzor_numer` jest pomijany. Rozdzielić odczyt URL przy wejściu od działania „Reset”, które obecnie może ponownie odczytać stary filtr tekstowy. Zaczekać na słowniki przed ustawieniem wartości filtrów.
- [ ] **Ustabilizować stronicowanie.** Pierwsze pobranie listy może ruszyć przed wypełnieniem selektora sortowania. Stosować `LIMIT/OFFSET` niezależnie od parametru `sort`, dodać jednoznaczny warunek rozstrzygający remisy i obsłużyć zmianę filtrów podczas pobierania.
- [ ] **Dokończyć nawigację szczegółów i historię.** Zweryfikować w schemacie obecność `prev_id` i `next_id` lub obliczać sąsiadów według ustalonej kolejności. Obsługa `popstate` wywołuje ładowanie, które znów robi `pushState`. Rozdzielić przejście do nowego wydania od odtworzenia widoku z historii.
- [ ] **Dokończyć spójny nagłówek sesji oraz obsługę ścieżek.** Lista ma pusty kontener logowania. Przy zewnętrznym `DATA_ROOT` trasa ikon dokleja nazwę katalogu bez separatora. Adres powrotu Auth0 podobnie zależy od końcowego ukośnika w `MY_URL`.
- [ ] **Uodpornić generowanie miniatur.** Równoległe pierwsze żądania mogą tworzyć ten sam katalog lub zapisywać ten sam plik. Użyć tworzenia katalogu bez konfliktu i zapisu atomowego. Ustalić odświeżanie po podmianie oryginału, a w widokach obsłużyć niedostępny skan.
- [ ] **Przygotować odtwarzalne uruchomienie i testy.** Udokumentować wymagane ustawienia i wersję SQLite, dostarczyć schemat lub sposób inicjalizacji oraz małą bazę testową i skany. Dodać testy listy, filtrów, uprawnień, transakcji edycji i miniaturek. Zweryfikować, czy zbędne zależności ORM i migracji można usunąć.

## P2 — Brakujące funkcje

- [ ] Dokończyć dodawanie miasta, autora i wydawcy z poziomu formularza albo usunąć opcję „Dodaj nowy” do czasu wdrożenia.
- [ ] Ustalić zakres dalszego katalogowania. Kod nie zawiera tworzenia ani usuwania wydań i wzorów, importu oraz dodawania lub wymiany skanów z interfejsu.
- [ ] Ustalić zakres filtrów i edycji. API przyjmuje rok, lecz lista nie ma pola roku. Katalog nie filtruje po tagach ani cenzurze. Formularz nie edytuje m.in. nakładu, cenzury i numeru wzoru.
