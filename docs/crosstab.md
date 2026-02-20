# crosstab – tabele krzyżowe

Generuje tabele krzyżowe: wyniki pytań w podziale na zmienne demograficzne (np. płeć, wiek, województwo).

## Użycie

```bash
python main.py crosstab <plik.xlsx> --config config.yaml --demographics M1,M2a,M10 [--output-dir output]
```

## Argumenty

| Argument | Opis |
|----------|------|
| `plik.xlsx` | Plik Excel z danymi |
| `--config`, `-c` | Plik konfiguracji YAML |
| `--demographics`, `-g` | **Wymagane.** ID pytań demograficznych po przecinku (np. M1,M2a,M10) |
| `--output-dir`, `-d` | Folder na wynik (domyślnie: `output`) |

## Przykład

```bash
python main.py crosstab ankieta.xlsx --config swieccy_config_final.yaml --demographics M1,M2a,M10,M11
```

## Wynik

Plik `{nazwa_pliku}_crosstabs.xlsx` z arkuszami:
- Dla pytań na skali: średnie wg grup demograficznych
- Dla pytań kategorialnych: częstości % wg grup
