# compare – porównanie dwóch ankiet

## Tryb z konfiguracją YAML (zalecany)

Podaj **oba** pliki YAML (`--config1`, `--config2`). Pytania są łączone po **`id`** z konfiguracji. W raporcie porównawczym są wyłącznie pytania z `is_demographic: false`, które występują w **obu** plikach YAML z tym samym `question_type` i tą samą liczbą kolumn. Dla każdej takiej pary generowane są:

- tabela: `N` i `%` dla obu grup,
- wykres słupkowy grupowany (dwie serie) z etykietami wartości nad słupkami.

Pytania występujące tylko w jednym kwestionariuszu (brak `id` w drugim YAML) są **pomijane** (bez błędu; w logu może pojawić się zestawienie liczby takich `id`).

Typy obsługiwane w tym trybie: `single_choice`, `numeric_scale`, `likert`, `multiple_choice`, `yes_no_matrix`.

### Użycie

```bash
python main.py compare <plik1.xlsx> <plik2.xlsx> \
  --config1 <ankieta1.yaml> --config2 <ankieta2.yaml> \
  [--label1 "Świeccy"] [--label2 "Duchowni"] [--output-dir output]
```

Same nazwy plików YAML są wczytywane z folderu `config/`, jeśli podasz samą nazwę (bez ścieżki).

### Przykład

```bash
python main.py compare swieccy.xlsx duchowni.xlsx \
  --config1 swieccy_config_final.yaml \
  --config2 duchowni_config_final.yaml \
  --label1 "Świeccy" --label2 "Duchowni"
```

Musisz podać **oba** `--config1` i `--config2` (istniejące pliki). Podanie tylko jednego z nich kończy działanie z komunikatem błędu.

### Wynik

- `porownanie_raport.docx` – raport Word z sekcjami, tabelami i wykresami
- `porownanie_raport.xlsx` – arkusz na każdą wygenerowaną tabelę porównawczą

## Tryb legacy (bez YAML)

Jeśli **nie** podasz `--config1` ani `--config2`, zachowuje się poprzednia logika: auto-detekcja pytań, dopasowanie po podobieństwie etykiet (pierwsze 40 znaków pierwszej kolumny), tylko `numeric_scale` / `likert`, raport ze **średnimi** (wykres poziomy `comparison_bar`).

## Argumenty

| Argument | Opis |
|----------|------|
| `plik1.xlsx`, `plik2.xlsx` | Dwa pliki Excel do porównania |
| `--config1`, `--config2` | YAML pierwszej i drugiej ankiety (mapowanie po `id`) |
| `--label1` | Etykieta pierwszej grupy (domyślnie: "Group 1") |
| `--label2` | Etykieta drugiej grupy (domyślnie: "Group 2") |
| `--output-dir`, `-d` | Folder na raporty (domyślnie: `output`) |

## Wagi

Jeśli plik ma kolumnę `Waga`, `weight` lub `wagi`, statystyki dla tej ankiety są ważone. Każdy plik jest traktowany osobno – np. pierwsza ankieta ważona, druga nieważona.
