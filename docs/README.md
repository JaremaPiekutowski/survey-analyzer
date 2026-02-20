# Dokumentacja Survey Analyzer

Narzędzie do analizy ankiet z plików Excel (XLSX). Generuje raporty DOCX i XLSX z wykresami i tabelami.

## Szybki start

1. Umieść plik z ankietą w folderze `input/`
2. Wykryj pytania i wygeneruj konfigurację:
   ```bash
   python main.py detect ankieta.xlsx --output config.yaml
   ```
3. Sprawdź i popraw `config.yaml`, potem wygeneruj raport:
   ```bash
   python main.py report ankieta.xlsx --config config.yaml
   ```

## Komendy

| Komenda | Opis |
|---------|------|
| [detect](detect.md) | Automatyczne wykrywanie pytań i eksport konfiguracji YAML |
| [report](report.md) | Generowanie raportu DOCX + XLSX |
| [crosstab](crosstab.md) | Tabele krzyżowe wg zmiennych demograficznych |
| [demographic-report](demographic-report.md) | Raport z podziałem na kategorie (płeć, wiek, wykształcenie itd.) |
| [compare](compare.md) | Porównanie dwóch ankiet |

## Konfiguracja

Szczegóły struktury pliku YAML: [config.md](config.md)

## Ścieżki plików

- **Excel** – domyślnie z folderu `input/` (jeśli podasz samą nazwę pliku)
- **Config** – domyślnie z folderu `config/` (jeśli podasz samą nazwę)
- **Raporty** – domyślnie do folderu `output/`

## Pomoc w linii poleceń

```bash
python main.py --help
python main.py detect --help
python main.py report --help
python main.py crosstab --help
python main.py demographic-report --help
python main.py compare --help
```
