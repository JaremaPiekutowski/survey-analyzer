# Survey Analyzer — XLSX Survey Analysis Tool

A command-line tool for analyzing survey data from Excel (XLSX) files. Generates DOCX reports with charts and tables, XLSX statistics sheets, and comparison reports between survey groups.

## Installation

```bash
pip install -e .
```

Requires Python 3.10+. Dependencies: pandas, openpyxl, matplotlib, scipy, python-docx, pyyaml.

## Quick Start

1. **Create the input folder** and place your survey Excel files there:
   ```
   mkdir input
   # Copy your survey.xlsx to input/
   ```

2. **Auto-detect questions** and generate a config file for review:
   ```bash
   python main.py detect survey.xlsx --output config.yaml
   ```
   (When you use a bare filename like `survey.xlsx`, the tool looks for it in the `input/` folder.)

3. **Review and edit** the generated `config.yaml`, then **generate the report**:
   ```bash
   python main.py report survey.xlsx --config config.yaml --title "My Survey Report"
   ```

## Example Configuration

An example configuration file with sample question definitions is provided in the project root:

- **`config.example.yaml`** — Copy this file to get started. It shows the structure for different question types (numeric scale, Likert, single choice, multiple choice). Adjust column indices and labels to match your survey.

```bash
cp config.example.yaml config.yaml
# Edit config.yaml to match your survey columns
```

## Usage

### 1. Auto-detect questions → YAML config for review

```bash
python main.py detect survey.xlsx --output config.yaml
```

Generates a YAML file with auto-detected questions. Review and adjust:
- Check `label` (parent question text)
- Check `column_labels` (sub-question labels)
- Split oversized groups, merge small ones
- Assign proper `id` (e.g. A1, B3, C2)
- Set `question_type: skip` to exclude a question

### 2. Generate report from config

```bash
python main.py report survey.xlsx --config config.yaml --title "Report title"
```

Generates:
- **DOCX** — Report with charts and tables
- **XLSX** — Spreadsheet with statistics

### 3. Cross-tabulation report

```bash
python main.py crosstab survey.xlsx --config config.yaml --demographics M1,M2a,M3
```

### 4. Comparison report (two surveys)

```bash
python main.py compare laity.xlsx clergy.xlsx --label1 "Laity" --label2 "Clergy"
```

## Input and Output

**Excel files** are read from the `input/` folder by default.
**Config files** are read from the `config/` folder when you pass a bare filename (e.g. `swieccy_config_final.yaml` → `config/swieccy_config_final.yaml`).
**Reports** (DOCX, XLSX) are written to the `output/` folder by default.

## Supported Question Types

| Type | Description | Chart |
|------|-------------|-------|
| `numeric_scale` | 0–10 scale (e.g. trust) | Horizontal bar means |
| `likert` | Scale with prefix "4: rather agree" | Horizontal bar means |
| `multiple_choice` | MENTIONED / NOT MENTIONED | Bar chart % selections |
| `single_choice` | Single categorical answer | Pie (≤3 cats.) or bar |
| `skip` | Exclude from report | — |

## YAML Config Structure

```yaml
questions:
  - id: 'A1'
    label: 'A1. Full parent question text'
    columns: [7, 8, 9, 10]          # column indices (0-based)
    column_labels:                    # full sub-question labels
      - 'Sub-question 1'
      - 'Sub-question 2'
    question_type: numeric_scale     # question type
    chart_type: horizontal_bar_means # chart type
    is_demographic: false
    scale_min: 0                     # min scale (for numeric/likert)
    scale_max: 10                    # max scale
    scale_labels:                     # value labels (for likert)
      1: 'strongly disagree'
      5: 'strongly agree'
    special_values: [6, 7]           # values to exclude (don't know, refuse)
```

## Project Structure

```
survey-analyzer/
├── main.py                  # CLI entry point
├── config.example.yaml     # Example configuration (copy and customize)
├── pyproject.toml
├── input/                  # Place your Excel survey files here
├── output/                 # Generated reports (DOCX, XLSX)
├── core/
│   ├── data_loader.py      # XLSX loading, auto-detection
│   └── statistics.py      # Weighted means, distributions, medians
├── charts/
│   └── chart_generator.py # matplotlib charts (bar, pie, comparison)
└── reports/
    ├── docx_builder.py     # DOCX report building
    └── xlsx_builder.py     # XLSX report building
```

## Documentation

For detailed documentation, see the inline help:

```bash
python main.py --help
python main.py detect --help
python main.py report --help
python main.py crosstab --help
python main.py compare --help
```
