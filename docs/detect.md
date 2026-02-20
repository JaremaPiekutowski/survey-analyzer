# detect – wykrywanie pytań

Automatycznie analizuje plik Excel i wykrywa typy pytań. Zapisuje wynik do pliku YAML, który możesz poprawić przed generowaniem raportu.

## Użycie

```bash
python main.py detect <plik.xlsx> [--output config.yaml]
```

## Argumenty

| Argument | Opis |
|----------|------|
| `plik.xlsx` | Plik Excel z danymi ankiety (z `input/` jeśli podasz samą nazwę) |
| `--output`, `-o` | Ścieżka do zapisu konfiguracji (domyślnie: `plik_config.yaml`) |

## Przykład

```bash
python main.py detect ankieta_swieccy.xlsx --output config/swieccy_config.yaml
```

## Co robi

1. Wczytuje plik Excel
2. Analizuje nagłówki kolumn i wykrywa wzorce pytań (np. A1., B3a., M2a.)
3. Klasyfikuje typy: skala numeryczna, Likert, jednokrotny wybór, wielokrotny wybór
4. Zapisuje konfigurację YAML

## Po wykryciu

Przejrzyj wygenerowany plik YAML i popraw:
- `label` – treść pytania
- `column_labels` – etykiety podpytań
- `question_type` – typ pytania
- `columns` – indeksy kolumn (0-based)
