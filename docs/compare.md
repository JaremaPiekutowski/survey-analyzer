# compare – porównanie dwóch ankiet

Porównuje dwie ankiety (np. świeccy vs duchowni). Dopasowuje pytania po etykietach i generuje raport z wykresami słupkowymi obok siebie.

## Użycie

```bash
python main.py compare <plik1.xlsx> <plik2.xlsx> [--label1 "Grupa 1"] [--label2 "Grupa 2"] [--output-dir output]
```

## Argumenty

| Argument | Opis |
|----------|------|
| `plik1.xlsx`, `plik2.xlsx` | Dwa pliki Excel do porównania |
| `--label1` | Etykieta pierwszej grupy (domyślnie: "Group 1") |
| `--label2` | Etykieta drugiej grupy (domyślnie: "Group 2") |
| `--output-dir`, `-d` | Folder na raporty (domyślnie: `output`) |

## Przykład

```bash
python main.py compare swieccy.xlsx duchowni.xlsx --label1 "Świeccy" --label2 "Duchowni"
```

## Wynik

- `porownanie_raport.docx` – raport Word z porównaniem średnich
- `porownanie_raport.xlsx` – arkusz Excel

## Wagi

Jeśli plik ma kolumnę `Waga`, `weight` lub `wagi`, statystyki dla tej ankiety są ważone. Każdy plik jest traktowany osobno – np. świeccy.xlsx z wagami vs duchowni.xlsx bez wag: pierwsza ankieta ważona, druga nieważona.

## Dopasowanie pytań

Narzędzie dopasowuje pytania między ankietami po podobieństwie etykiet (pierwsze 40 znaków). Porównywane są tylko pytania na skali (numeric_scale, likert).
