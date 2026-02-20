# report – raport główny

Generuje raport DOCX i XLSX z wynikami ankiety: tabele statystyk, wykresy słupkowe, kołowe itd.

## Użycie

```bash
python main.py report <plik.xlsx> [--config config.yaml] [--output-dir output] [--title "Tytuł"]
```

## Argumenty

| Argument | Opis |
|----------|------|
| `plik.xlsx` | Plik Excel z danymi |
| `--config`, `-c` | Plik konfiguracji YAML (opcjonalny – bez niego wykrywa pytania automatycznie) |
| `--output-dir`, `-d` | Folder na raporty (domyślnie: `output`) |
| `--title`, `-t` | Tytuł raportu |

## Przykład

```bash
python main.py report ankieta.xlsx --config swieccy_config_final.yaml --title "Ankieta świeccy 2024"
```

## Wynik

- `{nazwa_pliku}_raport.docx` – raport Word z tabelami i wykresami
- `{nazwa_pliku}_raport.xlsx` – arkusz Excel ze statystykami (jeden arkusz na pytanie)

## Typy pytań i wykresy

| Typ | Wykres |
|-----|--------|
| Skala numeryczna / Likert | Słupki ze średnimi |
| Jednokrotny wybór (≤3 opcje) | Wykres kołowy |
| Jednokrotny wybór (>3 opcje) | Słupki częstości |
| Wielokrotny wybór | Słupki % wskazań |

## Wagi

Jeśli w Excelu jest kolumna `waga`, `weight` lub `wagi`, narzędzie użyje jej do ważonych statystyk.
