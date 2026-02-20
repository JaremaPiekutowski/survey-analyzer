# demographic-report – raport z podziałem demograficznym

Raport, w którym każde pytanie nie-kategorialne jest analizowane osobno dla każdej kategorii demograficznej (płeć, wiek, wykształcenie, województwo itd.). Zawiera tabele krzyżowe, testy istotności i wykresy.

## Użycie

```bash
python main.py demographic-report <plik.xlsx> --config config.yaml [--output-dir output] [--title "Tytuł"]
```

## Argumenty

| Argument | Opis |
|----------|------|
| `plik.xlsx` | Plik Excel z danymi |
| `--config`, `-c` | **Wymagane.** Plik konfiguracji z `categorical_questions` |
| `--output-dir`, `-d` | Folder na raporty (domyślnie: `output`) |
| `--title`, `-t` | Tytuł raportu |

## Konfiguracja

W pliku YAML musisz mieć zdefiniowane `categorical_questions` – listę ID pytań używanych jako wymiary podziału:

```yaml
categorical_questions: [M1, M2a, M10, M11, M3, M4]
```

Jeśli brak tej listy, używane są pytania z `is_demographic: true`.

## Przykład

```bash
python main.py demographic-report ankieta_swieccy.xlsx --config swieccy_config_final.yaml
```

## Co zawiera raport

Dla każdego pytania nie-kategorialnego i każdej kategorii (np. M1 Płeć):

| Typ pytania | Tabela | Wykres | Test istotności |
|-------------|--------|--------|-----------------|
| Skala (Likert, 0–10) | Średnie wg grup | Słupki średnich | Kruskal-Wallis / Mann-Whitney |
| Jednokrotny / wielokrotny wybór | Częstości % wg grup | 100% stacked bar | Chi-kwadrat |

Plus jedno zdanie: czy istnieje istotna statystycznie różnica w zależności od kategorii (p &lt; 0,05).

## Skale – jeden wykres na podpytanie

Dla pytań z wieloma podpunktami (np. Likert z 13 stwierdzeniami) każdy podpunkt ma osobny wykres i tabelę – żeby wykresy nie były zbyt szerokie przy wielu kategoriach demograficznych.
