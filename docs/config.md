# Konfiguracja YAML

Plik konfiguracji opisuje strukturę pytań w ankiecie. Możesz go wygenerować komendą `detect` i potem poprawić.

## Struktura podstawowa

```yaml
# Opcjonalnie: pytania używane jako wymiary podziału w demographic-report
categorical_questions: [M1, M2a, M10, M11]

questions:
  - id: 'A1'
    label: 'A1. Pełna treść pytania'
    columns: [7, 8, 9, 10]
    column_labels:
      - 'Podpytanie 1'
      - 'Podpytanie 2'
    question_type: numeric_scale
    chart_type: horizontal_bar_means
    is_demographic: false
    scale_min: 0
    scale_max: 10
```

## Pola pytania

| Pole | Opis |
|------|------|
| `id` | Identyfikator (np. A1, M2a, D5b) |
| `label` | Pełna treść pytania |
| `columns` | Indeksy kolumn w Excelu (0 = pierwsza kolumna) |
| `column_labels` | Etykiety podpytań / opcji |
| `question_type` | Typ: `numeric_scale`, `likert`, `single_choice`, `multiple_choice` |
| `chart_type` | Rodzaj wykresu (zwykle ustawiany automatycznie) |
| `is_demographic` | Czy to pytanie demograficzne (płeć, wiek itd.) |

## Dla skal (numeric_scale, likert)

| Pole | Opis |
|------|------|
| `scale_min` | Minimalna wartość skali |
| `scale_max` | Maksymalna wartość skali |
| `scale_labels` | Etykiety wartości (np. 1: 'zdecydowanie się nie zgadzam') |
| `special_values` | Wartości do wykluczenia (np. 6=nie wiem, 7=odmowa) |

## Typy pytań

| Typ | Opis |
|-----|------|
| `numeric_scale` | Skala numeryczna (np. 0–10 zaufanie) |
| `likert` | Skala Likerta (np. 1–5 z etykietami) |
| `single_choice` | Jednokrotny wybór (jedna opcja) |
| `multiple_choice` | Wielokrotny wybór (MENTIONED / NOT MENTIONED) |

## categorical_questions

Lista ID pytań używanych jako wymiary podziału w `demographic-report`. Przykłady: płeć, wiek, wykształcenie, województwo, wielkość miejscowości.

Jeśli nie podasz tej listy, używane są pytania z `is_demographic: true`.

## Przykład pełny

Zobacz `config.example.yaml` w głównym folderze projektu.
