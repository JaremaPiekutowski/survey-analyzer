#!/usr/bin/env python3
"""
Survey Analyzer - Main CLI entry point.
Generates DOCX and XLSX reports from survey XLSX data files.

Usage:
  python main.py detect   <input.xlsx> [--output config.yaml]
  python main.py report   <input.xlsx> [--config config.yaml] [--output-dir ./output]
  python main.py crosstab <input.xlsx> --config config.yaml --demographics M1,M2a,M3
  python main.py compare  <file1.xlsx> <file2.xlsx> --config1 a.yaml --config2 b.yaml --label1 "Świeccy" --label2 "Duchowni"
  python main.py demographic-report <input.xlsx> --config config.yaml [--output-dir ./output]
  python main.py metric-report <input.xlsx> --config config.yaml [--output-dir ./output]
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import colorlog
import numpy as np
import pandas as pd

from core.data_loader import (
    load_xlsx, auto_detect_questions, get_numeric_data,
    export_config, load_config,
    QT_NUMERIC_SCALE, QT_LIKERT, QT_MULTI_CHOICE, QT_SINGLE_CHOICE,
    QT_YES_NO_MATRIX,
    CT_PIE, CT_FREQ_BAR, QuestionDef, apply_survey_profile_transforms,
    parse_yes_no_cell,
)
from core.statistics import (
    descriptive_stats, frequency_table, multiple_choice_table,
    multi_single_choice_frequency_pivot,
    cross_tab_means, cross_tab_frequencies,
    chi_square_test, test_group_differences, yes_no_matrix_table,
    open_ended_other_text_table,
    merge_two_frequency_tables, merge_two_option_tables,
    order_categories_for_merge, scale_series_to_category_labels,
)
from core.report_ordering import (
    format_section_title,
    order_frequency_dataframe,
    order_multiple_choice_dataframe,
    order_descriptive_stats,
    order_cross_tab_pivot,
    order_cross_tab_columns_polish,
    order_demo_category_rows,
)
from charts.chart_generator import (
    horizontal_bar_means, pie_chart, frequency_bar, grouped_bar_percent,
    comparison_bar, grouped_bar_two_groups,
    stacked_bar_100
)
from reports.docx_builder import ReportBuilder
from reports.xlsx_builder import XlsxReportBuilder


def _setup_logging(verbose: bool = False):
    """Configure colorlog for detailed, colorful output."""
    handler = colorlog.StreamHandler(sys.stdout)
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)-8s%(reset)s %(cyan)s%(name)s%(reset)s │ %(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        secondary_log_colors={},
        style="%",
    ))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)


logger = logging.getLogger(__name__)

INPUT_DIR = Path("input")
CONFIG_DIR = Path("config")

# W compare (YAML): dla tych id skal — jeden wykres i tabela średnich (wszystkie podpunkty), nie rozkładów.
COMPARE_MEANS_SCALE_IDS = frozenset({
    'A1', 'A1a', 'A2', 'A3a', 'A3b', 'C2', 'D1a', 'D1b', 'D5a',
})

# Szerokość wykresu w DOCX (cale) + osobna strona po tabeli — czytelny rozmiar.
COMPARE_DOCX_CHART_WIDTH_IN = 6.75
# Wykresy średnich dla długich bloków Likert — większy PNG i szerszy obraz w Word (jak A3b).
COMPARE_MEANS_TALL_FIG_IDS = frozenset({'A2', 'A3a', 'A3b', 'D1a', 'D1b'})
COMPARE_DOCX_CHART_WIDTH_TALL_IN = 7.35

# Compare: większa czcionka na wykresach średnich (tylko te id).
COMPARE_MEANS_FONT_SCALE_A2_A3A = 1.2

# Compare: poziome słupki grupowane (jak długie listy opcji).
COMPARE_HORIZONTAL_SINGLE_IDS = frozenset({"B3", "B3a", "D4"})
COMPARE_HORIZONTAL_MULTI_IDS = frozenset({"E3"})
COMPARE_HORIZONTAL_YES_NO_IDS = frozenset({"E4"})

# D1b — wspólne etykiety wierszy (świeccy); porównanie par mimo różnych brzmień w YAML duchownych.
COMPARE_D1B_ITEM_LABELS = [
    "Ważne jest dla niego/niej, aby sam/a podejmował/a decyzje w swoich własnych sprawach. Lubi wolność i niezależność od innych.",
    "Bardzo ważne jest dla niego/niej, aby pomagać otaczającym go ludziom. Pragnie dbać o ich dobro.",
    "Ważne jest dla niego/niej odnoszenie znaczących sukcesów. Ma nadzieję, że ludzie docenią jego/jej osiągnięcia.",
    "Ważne jest dla niego/niej, aby władza zapewniła mu/jej ochronę przed wszelkimi zagrożeniami. Pragnie, żeby państwo było silne, aby mogło bronić swych obywateli.",
    "Poszukuje przygód i lubi ryzykować. Chce mieć życie pełne wrażeń.",
    "Ważne jest dla niego/niej, aby zawsze zachowywać się poprawnie. Pragnie uniknąć postępowania, które ludzie mogliby uznać za niewłaściwe.",
    "Ważne jest dla niego/niej, aby inni ludzie go/ją szanowali. Chce, aby ludzie robili to, co im każe.",
    "Ważne jest dla niego/niej, aby być lojalnym wobec przyjaciół. Chce poświęcić się dla bliskich sobie osób.",
    "Jest głęboko przekonany/a, że ludzie powinni dbać o przyrodę. Ważna jest dla niego/niej troska o środowisko naturalne.",
    "Ważna jest dla niego/niej tradycja. Stara się postępować zgodnie z tradycjami religijnymi lub rodzinnymi.",
    "Poszukuje okazji, aby zabawić się. Ważne jest dla niego/niej, aby robić to, co sprawia mu/jej przyjemność.",
]


def _resolve_input_path(path: str) -> Path:
    """Resolve input path: bare filenames are read from input/ folder."""
    p = Path(path)
    if len(p.parts) == 1:
        return INPUT_DIR / p.name
    return p


def _demographic_slug(label: str, max_len: int = 60) -> str:
    """Create filesystem-safe slug from demographic question label.
    E.g. 'M1. Płeć respondenta' -> 'Plec_respondenta'
    """
    text = re.sub(r'^[A-Z]?\d+a?\.\s*', '', str(label or '').strip())
    for char in '\\/:*?"<>|':
        text = text.replace(char, '_')
    text = text.replace(' ', '_')
    text = re.sub(r'_+', '_', text).strip('_')
    if len(text) > max_len:
        text = text[:max_len].rstrip('_')
    return text or 'demograficzna'


def _resolve_config_path(path: str) -> Path:
    """Resolve config path: bare filenames are read from config/ folder."""
    p = Path(path)
    if len(p.parts) == 1:
        return CONFIG_DIR / p.name
    return p


def cmd_detect(args):
    """Auto-detect question types and export config YAML."""
    logger.info("═══ DETECT: Auto-detecting question types ═══")
    input_path = _resolve_input_path(args.input)
    logger.info("Step 1/4: Loading Excel file from %s", input_path)
    df = load_xlsx(str(input_path), header_row=0)
    logger.info("Step 2/4: Analyzing column structure and question types...")
    questions = auto_detect_questions(df)

    output = args.output or args.input.replace('.xlsx', '_config.yaml')
    logger.info("Step 3/4: Exporting config to %s", output)
    export_config(questions, output)

    from collections import Counter
    type_counts = Counter(q.question_type for q in questions)
    logger.info("Step 4/4: Detection complete")
    logger.info("─── Summary: %d question groups detected ───", len(questions))
    for qtype, count in type_counts.most_common():
        logger.info("  %s: %d", qtype, count)
    logger.info("Config saved to: %s", output)
    logger.info("Review and edit the YAML, then run 'report' command.")


def cmd_report(args):
    """Generate DOCX + XLSX report for a single survey."""
    logger.info("═══ REPORT: Generating survey report ═══")
    input_path = _resolve_input_path(args.input)
    logger.info("Step 1/6: Loading Excel file from %s", input_path)
    df = load_xlsx(str(input_path), header_row=0)

    config_path = _resolve_config_path(args.config) if args.config else None
    if config_path and config_path.exists():
        logger.info("Step 2/6: Loading question config from %s", config_path)
        questions, _, survey_profile = load_config(str(config_path))
        logger.info("Loaded %d questions from config", len(questions))
        df = apply_survey_profile_transforms(df, questions, survey_profile)
    else:
        if args.config:
            logger.warning("Config file not found: %s (looked in %s)", args.config,
                          config_path.resolve() if config_path else args.config)
        logger.info("Step 2/6: Auto-detecting questions (no config provided)")
        questions = auto_detect_questions(df)
        logger.info("Auto-detected %d question groups", len(questions))
        survey_profile = ""

    weight_col = None
    for col in df.columns:
        if str(col).lower().strip() in ('waga', 'weight', 'wagi'):
            weight_col = col
            break

    weights = None
    if weight_col:
        weights = pd.to_numeric(df[weight_col], errors='coerce').fillna(1.0)
        logger.info("Using weight column: %s", weight_col)
    else:
        logger.info("No weight column found, using unweighted analysis")

    out_dir = Path(args.output_dir or 'output')
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Step 3/6: Output directory: %s", out_dir.resolve())

    stem = input_path.stem
    report = ReportBuilder(title=args.title or f"Report: {stem}")
    xlsx_report = XlsxReportBuilder()
    logger.info("Step 4/6: Processing questions...")

    q_num = 0
    for q in questions:
        if q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT):
            q_num += 1
            logger.info("  [%s] %s... (scale/likert)", q.id, q.label[:50])

            data = get_numeric_data(df, q, weight_col)
            w = data.pop('_weight') if '_weight' in data.columns else weights
            stats = descriptive_stats(data, w)
            stats = order_descriptive_stats(stats, q)

            # Determine scale for chart
            s_min = q.scale_min if q.scale_min is not None else 0
            s_max = q.scale_max if q.scale_max is not None else 10

            # For Likert with special values (6=nie wiem, 7=odmowa), cap at 5
            if q.question_type == QT_LIKERT and q.special_values:
                actual_max = max(v for v in range(1, s_max+1) if v not in q.special_values)
                s_max = actual_max

            chart_title = q.id if q.id else f"Pytanie {q_num}"
            hbar_kw = {}
            if q.id == 'A2':
                hbar_kw = {'row_spacing': 1.1, 'bar_height': 0.63}
            chart_buf = horizontal_bar_means(stats, title=chart_title,
                                            scale_min=s_min, scale_max=s_max, **hbar_kw)

            report.add_section(format_section_title(q), level=2)
            report.add_table(stats, title="Statystyki opisowe")
            report.add_chart(chart_buf, width=6.0)

            xlsx_report.add_dataframe_sheet(stats, f"{q.id}_stats"[:31],
                                            title=f"{q.id}: {q.label}")

        elif q.question_type == QT_MULTI_CHOICE:
            q_num += 1
            logger.info("  [%s] %s... (multiple choice)", q.id, q.label[:50])

            data = get_numeric_data(df, q, weight_col)
            w = data.pop('_weight') if '_weight' in data.columns else weights
            freq = multiple_choice_table(data, w)
            freq = order_multiple_choice_dataframe(freq, q)

            chart_title = q.id if q.id else f"Pytanie {q_num}"
            chart_buf = frequency_bar(freq, title=chart_title, horizontal=True)

            report.add_section(format_section_title(q), level=2)
            report.add_table(freq, title="Rozkład odpowiedzi (% wskazań)")
            report.add_chart(chart_buf, width=6.0)

            xlsx_report.add_dataframe_sheet(freq, f"{q.id}_freq"[:31],
                                            title=f"{q.id}: {q.label}")

        elif q.question_type == QT_YES_NO_MATRIX:
            q_num += 1
            logger.info("  [%s] %s... (yes/no matrix)", q.id, q.label[:50])
            freq = yes_no_matrix_table(df, q, weight_col, weights)
            freq = order_multiple_choice_dataframe(freq, q)

            chart_title = q.id if q.id else f"Pytanie {q_num}"
            chart_buf = frequency_bar(freq, title=chart_title, horizontal=True)

            report.add_section(format_section_title(q), level=2)
            report.add_table(freq, title="Rozkład odpowiedzi (% odpowiedzi „Tak” oraz „Inne”)")
            report.add_chart(chart_buf, width=6.0)

            xlsx_report.add_dataframe_sheet(freq, f"{q.id}_freq"[:31],
                                            title=f"{q.id}: {q.label}")

            if len(q.open_ended_columns or []) >= 2:
                other_tbl = open_ended_other_text_table(df, q, weight_col, weights)
                if not other_tbl.empty:
                    report.add_section("Najczęściej wymieniane inne odpowiedzi", level=3)
                    report.add_table(
                        other_tbl,
                        title="Rozkład wzmianek w polu „Inne” (udział wśród wzmianek)",
                    )
                    ochart = frequency_bar(
                        other_tbl,
                        title=f"{q.id} – inne (tekst)",
                        horizontal=True,
                    )
                    report.add_chart(ochart, width=6.0)
                    safe_o = re.sub(r'[\[\]*?:/\\]', "_", f"{q.id}_inne_tekst")[:31]
                    xlsx_report.add_dataframe_sheet(
                        other_tbl,
                        safe_o,
                        title=f"{q.id}: najczęstsze inne (tekst)",
                    )

        elif q.question_type == QT_SINGLE_CHOICE:
            q_num += 1
            logger.info("  [%s] %s... (single choice)", q.id, q.label[:50])

            n_cols = len(q.columns)
            col_labels = q.column_labels or [""] * n_cols

            if q.id == "B5" and n_cols == 3:
                report.add_section(format_section_title(q), level=2)
                pivot = multi_single_choice_frequency_pivot(df, q, weights)
                chart_title = q.id if q.id else f"Pytanie {q_num}"
                chart_buf = grouped_bar_percent(pivot, title=chart_title)
                report.add_table(
                    pivot,
                    title="Rozkład odpowiedzi (%) — Matki, Ojca, Dziadków",
                )
                report.add_chart(chart_buf, width=6.5)
                xlsx_report.add_dataframe_sheet(
                    pivot,
                    re.sub(r'[\[\]*?:/\\]', "_", f"{q.id}_freq")[:31],
                    title=f"{q.id}: {q.label}",
                )
                continue

            if n_cols > 1:
                report.add_section(format_section_title(q), level=2)
            for ci in range(n_cols):
                col_name = df.columns[q.columns[ci]]
                freq = frequency_table(df[col_name], weights)
                freq = order_frequency_dataframe(freq, q)

                sub = (
                    str(col_labels[ci]).strip()
                    if ci < len(col_labels) and str(col_labels[ci]).strip()
                    else f"Kolumna {ci + 1}"
                )
                chart_title = q.id if q.id else f"Pytanie {q_num}"
                if n_cols > 1:
                    chart_title = f"{chart_title} – {sub}"
                    report.add_section(sub, level=3)
                else:
                    report.add_section(format_section_title(q), level=2)

                n_cat = len(freq)
                if n_cat <= 3 and q.chart_type == CT_PIE:
                    chart_buf = pie_chart(freq, title=chart_title)
                else:
                    chart_buf = frequency_bar(
                        freq, title=chart_title, horizontal=(n_cat > 4)
                    )

                report.add_table(freq, title="Rozkład odpowiedzi")
                report.add_chart(chart_buf, width=5.5 if n_cat <= 3 else 6.0)

                sheet_base = f"{q.id}_{sub}" if n_cols > 1 else f"{q.id}_freq"
                safe_sheet = re.sub(r'[\[\]*?:/\\]', "_", sheet_base)[:31]
                xlsx_report.add_dataframe_sheet(
                    freq,
                    safe_sheet,
                    title=f"{q.id}: {sub}" if n_cols > 1 else f"{q.id}: {q.label}",
                )

    # Save reports
    docx_path = out_dir / f"{stem}_raport.docx"
    xlsx_path = out_dir / f"{stem}_raport.xlsx"

    logger.info("Step 5/6: Building DOCX report...")
    report.save(str(docx_path))
    logger.info("Step 6/6: Building XLSX report...")
    xlsx_report.save(str(xlsx_path))

    logger.info("─── Report complete ───")
    logger.info("DOCX: %s", docx_path)
    logger.info("XLSX: %s", xlsx_path)
    logger.info("Questions processed: %d", q_num)


def _is_metric_report_question(q: QuestionDef) -> bool:
    """Pytania M* w raporcie metrycznym: id z prefiksem M i typ single_choice."""
    if not q.id or not q.id.startswith("M"):
        return False
    return q.question_type == QT_SINGLE_CHOICE


def cmd_metric_report(args):
    """Raport częstości pytań M* bez wag (N i % z surowych liczebności, jak układ raportu głównego)."""
    logger.info("═══ METRIC-REPORT: Raport metryczny (M*, bez wag) ═══")
    input_path = _resolve_input_path(args.input)
    logger.info("Step 1/4: Loading Excel file from %s", input_path)
    df = load_xlsx(str(input_path), header_row=0)

    config_path = _resolve_config_path(args.config) if args.config else None
    if not config_path or not config_path.exists():
        raise SystemExit("metric-report requires --config with question definitions")
    logger.info("Step 2/4: Loading config from %s", config_path)
    questions, _, survey_profile = load_config(str(config_path))
    df = apply_survey_profile_transforms(df, questions, survey_profile)
    logger.info("metric-report: bez wag — częstości z surowych N")

    out_dir = Path(args.output_dir or "output")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    report = ReportBuilder(title=args.title or f"Raport metryczny: {stem}")
    xlsx_report = XlsxReportBuilder()
    logger.info("Step 3/4: Processing pytań M (single_choice)...")

    q_num = 0
    for q in questions:
        if q.id and q.id.startswith("M") and q.question_type != QT_SINGLE_CHOICE:
            logger.warning(
                "metric-report: pomijam %s — typ %s (obsługiwane: single_choice)",
                q.id,
                q.question_type,
            )
            continue
        if not _is_metric_report_question(q):
            continue

        q_num += 1
        logger.info("  [%s] %s... (metryczny, bez wag)", q.id, q.label[:50])

        n_cols = len(q.columns)
        col_labels = q.column_labels or [""] * n_cols

        if n_cols > 1:
            report.add_section(format_section_title(q), level=2)
        for ci in range(n_cols):
            col_name = df.columns[q.columns[ci]]
            freq = frequency_table(df[col_name], None)
            freq = order_frequency_dataframe(freq, q)

            sub = (
                str(col_labels[ci]).strip()
                if ci < len(col_labels) and str(col_labels[ci]).strip()
                else f"Kolumna {ci + 1}"
            )
            chart_title = q.id if q.id else f"Pytanie {q_num}"
            if n_cols > 1:
                chart_title = f"{chart_title} – {sub}"
                report.add_section(sub, level=3)
            else:
                report.add_section(format_section_title(q), level=2)

            n_cat = len(freq)
            if n_cat <= 3 and q.chart_type == CT_PIE:
                chart_buf = pie_chart(freq, title=chart_title)
            else:
                chart_buf = frequency_bar(
                    freq, title=chart_title, horizontal=(n_cat > 4)
                )

            report.add_table(freq, title="Rozkład odpowiedzi (bez wag)")
            report.add_chart(chart_buf, width=5.5 if n_cat <= 3 else 6.0)

            sheet_base = f"{q.id}_{sub}" if n_cols > 1 else f"{q.id}_freq"
            safe_sheet = re.sub(r'[\[\]*?:/\\]', "_", sheet_base)[:31]
            xlsx_report.add_dataframe_sheet(
                freq,
                safe_sheet,
                title=f"{q.id}: {sub}" if n_cols > 1 else f"{q.id}: {q.label}",
            )

    docx_path = out_dir / f"{stem}_raport_metryczny.docx"
    xlsx_path = out_dir / f"{stem}_raport_metryczny.xlsx"

    logger.info("Step 4/4: Saving reports...")
    report.save(str(docx_path))
    xlsx_report.save(str(xlsx_path))

    logger.info("─── Metric report complete ───")
    logger.info("DOCX: %s", docx_path)
    logger.info("XLSX: %s", xlsx_path)
    logger.info("Sections (M*, single_choice): %d", q_num)


def cmd_crosstab(args):
    """Generate cross-tabulation report by demographics."""
    logger.info("═══ CROSSTAB: Generating cross-tabulations ═══")
    input_path = _resolve_input_path(args.input)
    logger.info("Step 1/5: Loading Excel file from %s", input_path)
    df = load_xlsx(str(input_path), header_row=0)

    config_path = _resolve_config_path(args.config) if args.config else None
    if config_path and config_path.exists():
        logger.info("Step 2/5: Loading config from %s", config_path)
        questions, _, survey_profile = load_config(str(config_path))
        df = apply_survey_profile_transforms(df, questions, survey_profile)
    else:
        if args.config:
            logger.warning("Config file not found: %s", config_path.resolve() if config_path else args.config)
        logger.info("Step 2/5: Auto-detecting questions")
        questions = auto_detect_questions(df)

    weight_col = None
    for col in df.columns:
        if str(col).lower().strip() in ('waga', 'weight', 'wagi'):
            weight_col = col
            break
    weights = pd.to_numeric(df[weight_col], errors='coerce').fillna(1.0) if weight_col else None
    if weight_col:
        logger.info("Using weight column: %s", weight_col)

    demo_ids = [d.strip() for d in args.demographics.split(',')]
    logger.info("Demographic variables: %s", demo_ids)

    demo_questions = [q for q in questions if q.id in demo_ids or q.is_demographic]
    if not demo_questions:
        for d_id in demo_ids:
            for i, col in enumerate(df.columns):
                if str(col).startswith(d_id):
                    demo_questions.append(QuestionDef(
                        id=d_id, label=str(col)[:80], columns=[i],
                        column_labels=[str(col)], question_type=QT_SINGLE_CHOICE,
                        chart_type=CT_FREQ_BAR, is_demographic=True
                    ))
                    break

    logger.info("Step 3/5: Found %d demographic dimensions: %s",
                len(demo_questions), [d.id for d in demo_questions])

    out_dir = Path(args.output_dir or 'output')
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    xlsx_ct = XlsxReportBuilder()
    data_questions = [q for q in questions if not q.is_demographic and
                      q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT, QT_SINGLE_CHOICE, QT_YES_NO_MATRIX)]
    logger.info("Step 4/5: Computing cross-tabs (%d data questions × %d demographics)...",
                len(data_questions), len(demo_questions))

    for demo_q in demo_questions:
        demo_col_name = df.columns[demo_q.columns[0]]
        demo_series = df[demo_col_name]

        for data_q in data_questions[:50]:  # limit for performance
            if data_q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT):
                # For scale questions: mean by demographic group for each item
                data = get_numeric_data(df, data_q, weight_col)

                for item_col in data.columns:
                    if item_col.startswith('_'):
                        continue
                    ct = cross_tab_means(data[item_col], demo_series, weights)
                    ct = order_demo_category_rows(ct, demo_q)
                    if len(ct) > 1:
                        sheet_name = f"{data_q.id}x{demo_q.id}"[:31]
                        title = f"{data_q.id} wg {demo_q.id}"
                        xlsx_ct.add_dataframe_sheet(ct, sheet_name, title)
                        break  # one sheet per question group, first item

            elif data_q.question_type == QT_YES_NO_MATRIX:
                data = get_numeric_data(df, data_q, weight_col)
                w = data.pop('_weight') if '_weight' in data.columns else weights
                for item_label in data_q.column_labels:
                    if item_label.startswith('_'):
                        continue
                    tak = data[item_label].map({1.0: 'Tak', 0.0: 'Nie'})
                    ct = cross_tab_frequencies(tak, demo_series, w)
                    ct = order_cross_tab_columns_polish(ct, demo_q)
                    idx = [x for x in ('Tak', 'Nie') if x in ct.index]
                    idx.extend(x for x in ct.index if x not in idx)
                    ct = ct.reindex(idx)
                    if len(ct) > 0:
                        sheet_name = f"{data_q.id}_{item_label}"[:31]
                        title = f"{data_q.id} {item_label} wg {demo_q.id}"
                        xlsx_ct.add_cross_tab_sheet(ct.rename_axis('Kategoria', axis=0), sheet_name, title)
                if data_q.open_ended_columns:
                    oec = data_q.open_ended_columns
                    if len(oec) >= 2:
                        yn_col = df.columns[oec[0]]
                        yn_series = df[yn_col].apply(parse_yes_no_cell)
                        tak_inne = yn_series.map({1.0: 'Tak', 0.0: 'Nie'})
                        ct = cross_tab_frequencies(tak_inne, demo_series, w)
                        ct = order_cross_tab_columns_polish(ct, demo_q)
                        idx = [x for x in ('Tak', 'Nie') if x in ct.index]
                        idx.extend(x for x in ct.index if x not in idx)
                        ct = ct.reindex(idx)
                        if len(ct) > 0:
                            sheet_name = f"{data_q.id}_Inne"[:31]
                            xlsx_ct.add_cross_tab_sheet(
                                ct.rename_axis('Kategoria', axis=0), sheet_name,
                                title=f"{data_q.id} Inne (Tak/Nie) wg {demo_q.id}",
                            )
                    else:
                        mask_inne = pd.Series(False, index=df.index)
                        for oi in oec:
                            if oi >= len(df.columns):
                                continue
                            coln = df.columns[oi]
                            txt = df[coln].apply(
                                lambda x: '' if pd.isna(x) else str(x).strip()
                            )
                            mask_inne |= (txt != '') & (txt.str.lower() != 'nan') & (txt != '-')
                        inne_ser = pd.Series(
                            np.where(mask_inne, 'Wskazano', 'Nie wskazano'),
                            index=df.index,
                        )
                        ct = cross_tab_frequencies(inne_ser, demo_series, w)
                        ct = order_cross_tab_columns_polish(ct, demo_q)
                        if len(ct) > 0:
                            sheet_name = f"{data_q.id}_Inne"[:31]
                            xlsx_ct.add_cross_tab_sheet(
                                ct.rename_axis('Kategoria', axis=0), sheet_name,
                                title=f"{data_q.id} Inne wg {demo_q.id}",
                            )

            elif data_q.question_type == QT_SINGLE_CHOICE:
                col_labels = data_q.column_labels or [""] * len(data_q.columns)
                for ci, cidx in enumerate(data_q.columns):
                    data_col_name = df.columns[cidx]
                    ct = cross_tab_frequencies(df[data_col_name], demo_series, weights)
                    ct = order_cross_tab_pivot(ct, data_q)
                    ct = order_cross_tab_columns_polish(ct, demo_q)
                    if len(ct) > 0:
                        sub = (
                            str(col_labels[ci]).strip()
                            if ci < len(col_labels) and str(col_labels[ci]).strip()
                            else f"c{ci}"
                        )
                        sheet_name = re.sub(
                            r'[\[\]*?:/\\]', '_', f"{data_q.id}_{sub}"
                        )[:31]
                        title = f"{data_q.id} {sub} wg {demo_q.id}"
                        xlsx_ct.add_cross_tab_sheet(ct, sheet_name, title)

    logger.info("Step 5/5: Saving XLSX...")
    xlsx_path = out_dir / f"{stem}_crosstabs.xlsx"
    xlsx_ct.save(str(xlsx_path))
    logger.info("─── Cross-tab report saved to: %s ───", xlsx_path)


def _significance_sentence(test_result: dict, demo_label: str, scale: bool = False) -> str:
    """Format one-sentence summary of statistical significance."""
    p = test_result.get('p_value', float('nan'))
    stat = test_result.get('statistic', float('nan'))
    test_name = test_result.get('test', '')
    if pd.isna(p) or pd.isna(stat):
        return f"Podział wg {demo_label}: Brak wystarczających danych do testu istotności."
    sig = p < 0.05
    stat_sym = 'χ²' if test_name == 'chi2' else ('H' if 'Kruskal' in test_name else 'U')
    if scale:
        diff_type = "średnich"
    else:
        diff_type = "rozkładzie odpowiedzi"
    if sig:
        return f"Podział wg {demo_label}: Istnieje istotna statystycznie różnica w {diff_type} ({stat_sym}={stat:.2f}, p={p:.4f})."
    return f"Podział wg {demo_label}: Nie stwierdzono istotnej statystycznie różnicy w {diff_type} ({stat_sym}={stat:.2f}, p={p:.4f})."


def cmd_demographic_report(args):
    """Generate report with demographic/categorical breakdowns."""
    logger.info("═══ DEMOGRAPHIC-REPORT: Raport z podziałem kategorialnym ═══")
    input_path = _resolve_input_path(args.input)
    logger.info("Step 1/6: Loading Excel file from %s", input_path)
    df = load_xlsx(str(input_path), header_row=0)

    config_path = _resolve_config_path(args.config) if args.config else None
    if not config_path or not config_path.exists():
        raise SystemExit("demographic-report requires --config with categorical_questions defined")
    logger.info("Step 2/6: Loading config from %s", config_path)
    questions, categorical_ids, survey_profile = load_config(str(config_path))
    logger.info("Loaded %d questions from config", len(questions))
    df = apply_survey_profile_transforms(df, questions, survey_profile)

    weight_col = None
    for col in df.columns:
        if str(col).lower().strip() in ('waga', 'weight', 'wagi'):
            weight_col = col
            break
    weights = pd.to_numeric(df[weight_col], errors='coerce').fillna(1.0) if weight_col else None
    if weight_col:
        logger.info("Using weight column: %s", weight_col)

    if categorical_ids:
        cat_questions = [q for q in questions if q.id in categorical_ids]
    else:
        cat_questions = [q for q in questions if q.is_demographic]
    if not cat_questions:
        raise SystemExit("No categorical questions found. Add categorical_questions to config or use is_demographic: true.")
    logger.info("Categorical dimensions: %s", [q.id for q in cat_questions])

    data_questions = [q for q in questions if q.id not in {c.id for c in cat_questions}
                     and q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT, QT_SINGLE_CHOICE, QT_MULTI_CHOICE,
                                             QT_YES_NO_MATRIX)]
    logger.info("Data questions to analyze: %d", len(data_questions))

    out_dir = Path(args.output_dir or 'output')
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    logger.info("Step 3/6: Generating separate report per categorical variable...")

    total_processed = 0
    for demo_q in cat_questions:
        logger.info("═══ Raport wg %s: %s ═══", demo_q.id, demo_q.label[:50])
        demo_col_name = df.columns[demo_q.columns[0]]
        demo_series = df[demo_col_name]
        report = ReportBuilder(
            title=args.title or f"Raport demograficzny: {stem}",
            subtitle=demo_q.label
        )
        xlsx_report = XlsxReportBuilder()
        processed = 0

        for data_q in data_questions:
            logger.info("  [%s] %s", data_q.id, data_q.label[:60])
            report.add_section(format_section_title(data_q), level=2)

            if data_q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT):
                data = get_numeric_data(df, data_q, weight_col)
                w = data.pop('_weight') if '_weight' in data.columns else weights
                s_min = data_q.scale_min if data_q.scale_min is not None else 0
                s_max = data_q.scale_max if data_q.scale_max is not None else 10
                if data_q.question_type == QT_LIKERT and data_q.special_values:
                    actual_max = max((v for v in range(1, s_max + 1) if v not in data_q.special_values), default=s_max)
                    s_max = actual_max

                for col_idx, item_label in enumerate(data_q.column_labels):
                    if item_label.startswith('_'):
                        continue
                    logger.info("    %s – %s", data_q.id, item_label[:50])
                    item_col = data[item_label]
                    ct = cross_tab_means(item_col, demo_series, w)
                    ct = order_demo_category_rows(ct, demo_q)
                    if len(ct) < 2:
                        continue
                    test_res = test_group_differences(item_col, demo_series)
                    chart_df = ct.rename(columns={'Kategoria': 'Item'})
                    hbar_kw = {}
                    if data_q.id == 'A2':
                        hbar_kw = {'row_spacing': 1.1, 'bar_height': 0.63}
                    chart_buf = horizontal_bar_means(chart_df, title=f"{data_q.id} – {item_label} – podział wg {demo_q.label}",
                                                    scale_min=s_min, scale_max=s_max, value_col='Średnia', **hbar_kw)
                    sub_title = f"{item_label} – podział wg {demo_q.label}"
                    report.add_section(sub_title, level=3)
                    report.add_table(ct, title="Średnie wg grup")
                    report.add_chart(chart_buf, width=6.0)
                    report.add_paragraph(_significance_sentence(test_res, demo_q.label, scale=True))
                    sheet_name = f"{data_q.id}_{col_idx}"[:31]
                    xlsx_report.add_dataframe_sheet(ct, sheet_name, title=sub_title)
                    processed += 1

            elif data_q.question_type == QT_YES_NO_MATRIX:
                data = get_numeric_data(df, data_q, weight_col)
                w = data.pop('_weight') if '_weight' in data.columns else weights
                for col_idx, item_label in enumerate(data_q.column_labels):
                    if item_label.startswith('_'):
                        continue
                    logger.info("    [%s] %s", data_q.id, item_label[:50])
                    tak = data[item_label].map({1.0: 'Tak', 0.0: 'Nie'})
                    ct = cross_tab_frequencies(tak, demo_series, w)
                    ct = order_cross_tab_columns_polish(ct, demo_q)
                    idx = [x for x in ('Tak', 'Nie') if x in ct.index]
                    idx.extend(x for x in ct.index if x not in idx)
                    ct = ct.reindex(idx)
                    if ct.empty or len(ct.columns) < 2:
                        continue
                    test_res = chi_square_test(tak, demo_series, w)
                    chart_buf = stacked_bar_100(ct, title=f"{data_q.id} – {item_label} wg {demo_q.label}")
                    sub_title = f"{item_label} – podział wg {demo_q.label}"
                    report.add_section(sub_title, level=3)
                    ct_display = ct.rename_axis('Kategoria', axis=0).reset_index()
                    report.add_table(ct_display, title="Częstości % wg grup")
                    report.add_chart(chart_buf, width=6.0)
                    report.add_paragraph(_significance_sentence(test_res, demo_q.label, scale=False))
                    sheet_name = f"{data_q.id}_{col_idx}"[:31]
                    xlsx_report.add_cross_tab_sheet(ct.rename_axis('Kategoria', axis=0), sheet_name, title=sub_title)
                    processed += 1
                if data_q.open_ended_columns:
                    oec = data_q.open_ended_columns
                    if len(oec) >= 2:
                        yn_col = df.columns[oec[0]]
                        yn_series = df[yn_col].apply(parse_yes_no_cell)
                        inne_ser = yn_series.map({1.0: 'Tak', 0.0: 'Nie'})
                        ct = cross_tab_frequencies(inne_ser, demo_series, w)
                        ct = order_cross_tab_columns_polish(ct, demo_q)
                        if not ct.empty and len(ct.columns) >= 2:
                            test_res = chi_square_test(inne_ser, demo_series, w)
                            chart_buf = stacked_bar_100(
                                ct, title=f"{data_q.id} – Inne (Tak/Nie) wg {demo_q.label}"
                            )
                            sub_title = f"Inne (jakie?) – Tak/Nie – podział wg {demo_q.label}"
                            report.add_section(sub_title, level=3)
                            ct_display = ct.rename_axis('Kategoria', axis=0).reset_index()
                            report.add_table(ct_display, title="Częstości % wg grup")
                            report.add_chart(chart_buf, width=6.0)
                            report.add_paragraph(
                                _significance_sentence(test_res, demo_q.label, scale=False)
                            )
                            sheet_name = f"{data_q.id}_inne"[:31]
                            xlsx_report.add_cross_tab_sheet(
                                ct.rename_axis('Kategoria', axis=0), sheet_name, title=sub_title
                            )
                            processed += 1
                    else:
                        mask_inne = pd.Series(False, index=df.index)
                        for oi in oec:
                            if oi >= len(df.columns):
                                continue
                            coln = df.columns[oi]
                            txt = df[coln].apply(
                                lambda x: '' if pd.isna(x) else str(x).strip()
                            )
                            mask_inne |= (txt != '') & (txt.str.lower() != 'nan') & (txt != '-')
                        inne_ser = pd.Series(
                            np.where(mask_inne, 'Wskazano', 'Nie wskazano'),
                            index=df.index,
                        )
                        ct = cross_tab_frequencies(inne_ser, demo_series, w)
                        ct = order_cross_tab_columns_polish(ct, demo_q)
                        if ct.empty or len(ct.columns) < 2:
                            pass
                        else:
                            test_res = chi_square_test(inne_ser, demo_series, w)
                            chart_buf = stacked_bar_100(
                                ct, title=f"{data_q.id} – Inne wg {demo_q.label}"
                            )
                            sub_title = f"Inne (jakie?) – podział wg {demo_q.label}"
                            report.add_section(sub_title, level=3)
                            ct_display = ct.rename_axis('Kategoria', axis=0).reset_index()
                            report.add_table(ct_display, title="Częstości % wg grup")
                            report.add_chart(chart_buf, width=6.0)
                            report.add_paragraph(
                                _significance_sentence(test_res, demo_q.label, scale=False)
                            )
                            sheet_name = f"{data_q.id}_inne"[:31]
                            xlsx_report.add_cross_tab_sheet(
                                ct.rename_axis('Kategoria', axis=0), sheet_name, title=sub_title
                            )
                            processed += 1

            elif data_q.question_type == QT_SINGLE_CHOICE:
                logger.info("    [%s] single_choice", data_q.id)
                col_labels = data_q.column_labels or [""] * len(data_q.columns)
                col_pairs = list(enumerate(data_q.columns))
                if data_q.id == "B5" and len(data_q.columns) == 3:
                    col_pairs = [(0, data_q.columns[0])]
                    logger.info(
                        "    [%s] B5: w podziale demograficznym tylko „Matki” "
                        "(pełna tabela zbiorcza w raporcie głównym)",
                        data_q.id,
                    )
                for ci, cidx in col_pairs:
                    data_col_name = df.columns[cidx]
                    ct = cross_tab_frequencies(df[data_col_name], demo_series, weights)
                    ct = order_cross_tab_pivot(ct, data_q)
                    ct = order_cross_tab_columns_polish(ct, demo_q)
                    if ct.empty or len(ct.columns) < 2:
                        continue
                    test_res = chi_square_test(df[data_col_name], demo_series, weights)
                    sub = (
                        str(col_labels[ci]).strip()
                        if ci < len(col_labels) and str(col_labels[ci]).strip()
                        else f"c{ci}"
                    )
                    chart_buf = stacked_bar_100(
                        ct, title=f"{data_q.id} – {sub} wg {demo_q.label}"
                    )
                    sub_title = f"{data_q.label} – {sub} – podział wg {demo_q.label}"
                    report.add_section(sub_title, level=3)
                    ct_display = ct.rename_axis('Kategoria', axis=0).reset_index()
                    report.add_table(ct_display, title="Częstości % wg grup")
                    report.add_chart(chart_buf, width=6.0)
                    report.add_paragraph(_significance_sentence(test_res, demo_q.label, scale=False))
                    sheet_name = re.sub(r'[\[\]*?:/\\]', '_', f"{data_q.id}_{sub}")[:31]
                    xlsx_report.add_cross_tab_sheet(
                        ct.rename_axis('Kategoria', axis=0), sheet_name,
                        title=f"{data_q.id} {sub} wg {demo_q.label}",
                    )
                    processed += 1

            elif data_q.question_type == QT_MULTI_CHOICE:
                data = get_numeric_data(df, data_q, weight_col)
                w = data.pop('_weight') if '_weight' in data.columns else weights
                for col_idx, item_label in enumerate(data_q.column_labels):
                    if item_label.startswith('_'):
                        continue
                    logger.info("    [%s] %s", data_q.id, item_label[:50])
                    item_series = (data[item_label] == 1).replace({True: 'Wskazano', False: 'Nie wskazano'})
                    ct = cross_tab_frequencies(item_series, demo_series, w)
                    ct = order_cross_tab_columns_polish(ct, demo_q)
                    if ct.empty or len(ct.columns) < 2:
                        continue
                    test_res = chi_square_test(item_series, demo_series, w)
                    chart_buf = stacked_bar_100(ct, title=f"{data_q.id} – {item_label} wg {demo_q.label}")
                    sub_title = f"{item_label} – podział wg {demo_q.label}"
                    report.add_section(sub_title, level=3)
                    ct_display = ct.rename_axis('Kategoria', axis=0).reset_index()
                    report.add_table(ct_display, title="Częstości % wg grup")
                    report.add_chart(chart_buf, width=6.0)
                    report.add_paragraph(_significance_sentence(test_res, demo_q.label, scale=False))
                    sheet_name = f"{data_q.id}_{col_idx}"[:31]
                    xlsx_report.add_cross_tab_sheet(ct.rename_axis('Kategoria', axis=0), sheet_name, title=sub_title)
                    processed += 1

        demo_slug = _demographic_slug(demo_q.label)
        docx_path = out_dir / f"{stem}_raport_demograficzny_{demo_slug}.docx"
        xlsx_path = out_dir / f"{stem}_raport_demograficzny_{demo_slug}.xlsx"
        logger.info("  Saving %s...", docx_path.name)
        report.save(str(docx_path))
        logger.info("  Saving %s...", xlsx_path.name)
        xlsx_report.save(str(xlsx_path))
        total_processed += processed
        logger.info("  Done: %d sections", processed)

    logger.info("─── Demographic report complete ───")
    logger.info("Generated %d report pairs (DOCX + XLSX per variable)", len(cat_questions))
    logger.info("Total sections: %d", total_processed)


def _safe_sheet_name(base: str) -> str:
    return re.sub(r'[\[\]*?:/\\]', "_", base)[:31]


def _cmd_compare_legacy(
    df1, df2, weight_col1, weight_col2, weights1, weights2,
    label1, label2, out_dir: Path,
):
    """Previous behaviour: auto-detect and match scale/likert by label similarity (means)."""
    logger.info("Step 3/5: Auto-detecting questions in both surveys...")
    questions1 = auto_detect_questions(df1)
    questions2 = auto_detect_questions(df2)
    logger.info("Survey 1: %d scale/likert questions | Survey 2: %d scale/likert questions",
                sum(1 for q in questions1 if q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT)),
                sum(1 for q in questions2 if q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT)))

    report = ReportBuilder(title=f"Porównanie: {label1} vs {label2}")
    xlsx_report = XlsxReportBuilder()
    logger.info("Step 4/5: Matching and comparing questions (legacy: średnie)...")

    matched = 0
    for q1 in questions1:
        if q1.question_type not in (QT_NUMERIC_SCALE, QT_LIKERT):
            continue

        best_match = None
        for q2 in questions2:
            if q2.question_type != q1.question_type:
                continue
            if q1.column_labels and q2.column_labels:
                l1 = q1.column_labels[0][:40]
                l2 = q2.column_labels[0][:40]
                if l1 == l2 or l1 in l2 or l2 in l1:
                    best_match = q2
                    break

        if best_match:
            matched += 1
            logger.info("  Matched [%s]: %s", q1.id, q1.label[:50])
            data1 = get_numeric_data(df1, q1, weight_col1)
            data2 = get_numeric_data(df2, best_match, weight_col2)
            w1 = data1.pop('_weight') if '_weight' in data1.columns else weights1
            w2 = data2.pop('_weight') if '_weight' in data2.columns else weights2

            stats1 = descriptive_stats(data1, w1)
            stats2 = descriptive_stats(data2, w2)

            s_min = q1.scale_min or 0
            s_max = q1.scale_max or 10

            chart_buf = comparison_bar(stats1, stats2, label1, label2,
                                       title=q1.id, scale_min=s_min, scale_max=s_max)

            report.add_section(format_section_title(q1), level=2)

            merged = stats1[['Item', 'N', 'Średnia', 'Mediana']].rename(
                columns={'N': f'N ({label1})', 'Średnia': f'Śr. ({label1})', 'Mediana': f'Med. ({label1})'}
            ).merge(
                stats2[['Item', 'N', 'Średnia', 'Mediana']].rename(
                    columns={'N': f'N ({label2})', 'Średnia': f'Śr. ({label2})', 'Mediana': f'Med. ({label2})'}
                ), on='Item', how='outer'
            )

            report.add_table(merged)
            report.add_chart(
                chart_buf, width=COMPARE_DOCX_CHART_WIDTH_IN, page_break_before=True,
            )

            xlsx_report.add_dataframe_sheet(merged, _safe_sheet_name(f"{q1.id}_cmp"))

    docx_path = out_dir / "porownanie_raport.docx"
    xlsx_path = out_dir / "porownanie_raport.xlsx"

    logger.info("Step 5/5: Saving reports...")
    report.save(str(docx_path))
    xlsx_report.save(str(xlsx_path))

    logger.info("─── Comparison complete ───")
    logger.info("Matched questions: %d", matched)
    logger.info("DOCX: %s", docx_path)
    logger.info("XLSX: %s", xlsx_path)


def _cmd_compare_from_configs(
    df1, df2, weight_col1, weight_col2, weights1, weights2,
    config1_path: Path, config2_path: Path,
    label1: str, label2: str, out_dir: Path,
):
    """Map questions by id from two YAML configs; grouped bar charts + frequency tables."""
    logger.info("Step 3/5: Loading configs %s and %s", config1_path, config2_path)
    questions1, _, prof1 = load_config(str(config1_path))
    questions2, _, prof2 = load_config(str(config2_path))
    df1 = apply_survey_profile_transforms(df1, questions1, prof1)
    df2 = apply_survey_profile_transforms(df2, questions2, prof2)

    by_id2 = {q.id: q for q in questions2}
    ids1_nd = {q.id for q in questions1 if not q.is_demographic}
    ids2_nd = {q.id for q in questions2 if not q.is_demographic}
    only1 = ids1_nd - ids2_nd
    only2 = ids2_nd - ids1_nd
    if only1:
        logger.info("compare: pominięto %d pytań tylko w pierwszym kwestionariuszu (brak id w drugim YAML)",
                    len(only1))
        logger.debug("  id: %s", sorted(only1))
    if only2:
        logger.info("compare: pominięto %d pytań tylko w drugim kwestionariuszu (brak id w pierwszym YAML)",
                    len(only2))
        logger.debug("  id: %s", sorted(only2))

    report = ReportBuilder(title=f"Porównanie: {label1} vs {label2}")
    xlsx_report = XlsxReportBuilder()
    logger.info("Step 4/5: Porównanie rozkładów (YAML po id)...")

    pct1 = f'% ({label1})'
    pct2 = f'% ({label2})'
    ncol1 = f'N ({label1})'
    ncol2 = f'N ({label2})'
    matched = 0

    for q1 in questions1:
        if q1.is_demographic:
            continue
        if q1.id not in by_id2:
            continue
        q2 = by_id2[q1.id]
        if q2.is_demographic:
            continue
        if q1.question_type != q2.question_type:
            logger.warning("compare: pomijam %s — różne typy: %s vs %s",
                           q1.id, q1.question_type, q2.question_type)
            continue
        if len(q1.columns) != len(q2.columns):
            logger.warning("compare: pomijam %s — różna liczba kolumn (%d vs %d)",
                           q1.id, len(q1.columns), len(q2.columns))
            continue

        if q1.question_type == QT_SINGLE_CHOICE:
            n_cols = len(q1.columns)
            col_labels = q1.column_labels or [""] * n_cols
            if n_cols > 1:
                report.add_section(format_section_title(q1), level=2)
            for ci in range(n_cols):
                col_name1 = df1.columns[q1.columns[ci]]
                col_name2 = df2.columns[q2.columns[ci]]
                freq1 = frequency_table(df1[col_name1], weights1)
                freq2 = frequency_table(df2[col_name2], weights2)
                ordered = order_categories_for_merge(freq1, freq2, q1)
                merged = merge_two_frequency_tables(
                    freq1, freq2, label1, label2, ordered_categories=ordered,
                )
                sub = (
                    str(col_labels[ci]).strip()
                    if ci < len(col_labels) and str(col_labels[ci]).strip()
                    else f"Kolumna {ci + 1}"
                )
                chart_title = q1.id if n_cols == 1 else f"{q1.id} – {sub}"
                if n_cols == 1:
                    report.add_section(format_section_title(q1), level=2)
                else:
                    report.add_section(sub, level=3)
                sc_h = q1.id in COMPARE_HORIZONTAL_SINGLE_IDS
                fig_sc = None
                if sc_h:
                    nc = len(merged)
                    fig_sc = (14, max(12, nc * 0.72 + 4.5))
                chart_buf = grouped_bar_two_groups(
                    merged,
                    title=chart_title,
                    category_col='Kategoria',
                    value_cols=(pct1, pct2),
                    n_cols=(ncol1, ncol2),
                    legend_labels=(label1, label2),
                    horizontal=sc_h,
                    figsize=fig_sc,
                )
                report.add_table(merged, title="Rozkład odpowiedzi")
                report.add_chart(
                    chart_buf,
                    width=COMPARE_DOCX_CHART_WIDTH_TALL_IN if sc_h else COMPARE_DOCX_CHART_WIDTH_IN,
                    page_break_before=True,
                )
                sn = f"{q1.id}_{ci}" if n_cols > 1 else f"{q1.id}_cmp"
                xlsx_report.add_dataframe_sheet(merged, _safe_sheet_name(sn))
                matched += 1

        elif q1.question_type in (QT_NUMERIC_SCALE, QT_LIKERT):
            data1 = get_numeric_data(df1, q1, weight_col1)
            data2 = get_numeric_data(df2, q2, weight_col2)
            w1 = data1.pop('_weight') if '_weight' in data1.columns else weights1
            w2 = data2.pop('_weight') if '_weight' in data2.columns else weights2
            n_cols = len(q1.columns)
            col_labels = q1.column_labels or [""] * n_cols

            if q1.id in COMPARE_MEANS_SCALE_IDS:
                stats1 = descriptive_stats(data1, w1)
                stats2 = descriptive_stats(data2, w2)
                if q1.id == "D1b":
                    stats1 = stats1.reset_index(drop=True)
                    stats2 = stats2.reset_index(drop=True)
                    for i, lab in enumerate(COMPARE_D1B_ITEM_LABELS):
                        if i < len(stats1):
                            stats1.at[i, "Item"] = lab
                        if i < len(stats2):
                            stats2.at[i, "Item"] = lab
                else:
                    stats1 = order_descriptive_stats(stats1, q1)
                s_min = q1.scale_min if q1.scale_min is not None else 0
                s_max = q1.scale_max if q1.scale_max is not None else 10
                if q1.question_type == QT_LIKERT and q1.special_values:
                    valid_vals = [
                        v for v in range(1, int(s_max) + 1)
                        if v not in q1.special_values
                    ]
                    if valid_vals:
                        s_max = max(valid_vals)

                n_items = len(stats1)
                if q1.id in COMPARE_MEANS_TALL_FIG_IDS:
                    cmp_figsize = (15, max(14, n_items * 1.12 + 5))
                    docx_w = COMPARE_DOCX_CHART_WIDTH_TALL_IN
                else:
                    cmp_figsize = None
                    docx_w = COMPARE_DOCX_CHART_WIDTH_IN

                cmp_font = (
                    COMPARE_MEANS_FONT_SCALE_A2_A3A
                    if q1.id in ("A2", "A3a")
                    else 1.0
                )
                chart_buf = comparison_bar(
                    stats1, stats2, label1, label2,
                    title=format_section_title(q1), scale_min=s_min, scale_max=s_max,
                    figsize=cmp_figsize,
                    font_scale=cmp_font,
                    sort_by_mean=(q1.id != "D1b"),
                )
                report.add_section(format_section_title(q1), level=2)
                merged = stats1[['Item', 'N', 'Średnia', 'Mediana']].rename(
                    columns={
                        'N': f'N ({label1})',
                        'Średnia': f'Śr. ({label1})',
                        'Mediana': f'Med. ({label1})',
                    }
                ).merge(
                    stats2[['Item', 'N', 'Średnia', 'Mediana']].rename(
                        columns={
                            'N': f'N ({label2})',
                            'Średnia': f'Śr. ({label2})',
                            'Mediana': f'Med. ({label2})',
                        }
                    ),
                    on='Item',
                    how='outer',
                )
                report.add_table(merged, title="Statystyki opisowe")
                report.add_chart(
                    chart_buf, width=docx_w, page_break_before=True,
                )
                xlsx_report.add_dataframe_sheet(merged, _safe_sheet_name(f"{q1.id}_cmp"))
                matched += 1
            else:
                if n_cols > 1:
                    report.add_section(format_section_title(q1), level=2)
                for ci in range(n_cols):
                    k1 = q1.column_labels[ci]
                    k2 = q2.column_labels[ci]
                    s1 = scale_series_to_category_labels(data1[k1], q1)
                    s2 = scale_series_to_category_labels(data2[k2], q2)
                    freq1 = frequency_table(s1, w1)
                    freq2 = frequency_table(s2, w2)
                    ordered = order_categories_for_merge(freq1, freq2, q1)
                    merged = merge_two_frequency_tables(
                        freq1, freq2, label1, label2, ordered_categories=ordered,
                    )
                    sub = (
                        str(col_labels[ci]).strip()
                        if ci < len(col_labels) and str(col_labels[ci]).strip()
                        else f"Pozycja {ci + 1}"
                    )
                    chart_title = q1.id if n_cols == 1 else f"{q1.id} – {sub}"
                    if n_cols == 1:
                        report.add_section(format_section_title(q1), level=2)
                    else:
                        report.add_section(sub, level=3)
                    chart_buf = grouped_bar_two_groups(
                        merged,
                        title=chart_title,
                        category_col='Kategoria',
                        value_cols=(pct1, pct2),
                        n_cols=(ncol1, ncol2),
                        legend_labels=(label1, label2),
                    )
                    report.add_table(merged, title="Rozkład odpowiedzi")
                    report.add_chart(
                        chart_buf, width=COMPARE_DOCX_CHART_WIDTH_IN, page_break_before=True,
                    )
                    sn = f"{q1.id}_{ci}" if n_cols > 1 else f"{q1.id}_cmp"
                    xlsx_report.add_dataframe_sheet(merged, _safe_sheet_name(sn))
                    matched += 1

        elif q1.question_type == QT_MULTI_CHOICE:
            data1 = get_numeric_data(df1, q1, weight_col1)
            data2 = get_numeric_data(df2, q2, weight_col2)
            w1 = data1.pop('_weight') if '_weight' in data1.columns else weights1
            w2 = data2.pop('_weight') if '_weight' in data2.columns else weights2
            tbl1 = multiple_choice_table(data1, w1)
            tbl2 = multiple_choice_table(data2, w2)
            merged = merge_two_option_tables(tbl1, tbl2, label1, label2, q1)
            report.add_section(format_section_title(q1), level=2)
            mc_h = q1.id == "B8a" or q1.id in COMPARE_HORIZONTAL_MULTI_IDS
            fig_mc = None
            if mc_h:
                nc = len(merged)
                fig_mc = (14, max(12, nc * 0.72 + 4.5))
            chart_buf = grouped_bar_two_groups(
                merged,
                title=format_section_title(q1),
                category_col='Opcja',
                value_cols=(pct1, pct2),
                n_cols=(ncol1, ncol2),
                legend_labels=(label1, label2),
                horizontal=mc_h,
                figsize=fig_mc,
            )
            report.add_table(merged, title="Rozkład odpowiedzi")
            report.add_chart(
                chart_buf,
                width=COMPARE_DOCX_CHART_WIDTH_TALL_IN if mc_h else COMPARE_DOCX_CHART_WIDTH_IN,
                page_break_before=True,
            )
            xlsx_report.add_dataframe_sheet(merged, _safe_sheet_name(f"{q1.id}_cmp"))
            matched += 1

        elif q1.question_type == QT_YES_NO_MATRIX:
            tbl1 = yes_no_matrix_table(df1, q1, weight_col1, weights1)
            tbl2 = yes_no_matrix_table(df2, q2, weight_col2, weights2)
            if tbl1.empty and tbl2.empty:
                logger.warning("compare: pomijam %s — brak danych yes/no", q1.id)
                continue
            merged = merge_two_option_tables(tbl1, tbl2, label1, label2, q1)
            report.add_section(format_section_title(q1), level=2)
            yn_h = q1.id in COMPARE_HORIZONTAL_YES_NO_IDS
            fig_yn = None
            if yn_h:
                nc = len(merged)
                fig_yn = (14, max(12, nc * 0.72 + 4.5))
            chart_buf = grouped_bar_two_groups(
                merged,
                title=format_section_title(q1),
                category_col='Opcja',
                value_cols=(pct1, pct2),
                n_cols=(ncol1, ncol2),
                legend_labels=(label1, label2),
                horizontal=yn_h,
                figsize=fig_yn,
            )
            report.add_table(merged, title="Rozkład odpowiedzi")
            report.add_chart(
                chart_buf,
                width=COMPARE_DOCX_CHART_WIDTH_TALL_IN if yn_h else COMPARE_DOCX_CHART_WIDTH_IN,
                page_break_before=True,
            )
            xlsx_report.add_dataframe_sheet(merged, _safe_sheet_name(f"{q1.id}_cmp"))
            matched += 1

        else:
            logger.debug("compare: pomijam %s — typ %s nieobsługiwany w porównaniu",
                         q1.id, q1.question_type)

    docx_path = out_dir / "porownanie_raport.docx"
    xlsx_path = out_dir / "porownanie_raport.xlsx"

    logger.info("Step 5/5: Saving reports...")
    report.save(str(docx_path))
    xlsx_report.save(str(xlsx_path))

    logger.info("─── Comparison complete ───")
    logger.info("Sekcje porównawcze: %d", matched)
    logger.info("DOCX: %s", docx_path)
    logger.info("XLSX: %s", xlsx_path)


def cmd_compare(args):
    """Generate comparison report for two surveys."""
    logger.info("═══ COMPARE: Comparing two surveys ═══")
    input1_path = _resolve_input_path(args.input1)
    input2_path = _resolve_input_path(args.input2)
    logger.info("Step 1/5: Loading first survey from %s", input1_path)
    df1 = load_xlsx(str(input1_path), header_row=0)
    logger.info("Step 2/5: Loading second survey from %s", input2_path)
    df2 = load_xlsx(str(input2_path), header_row=0)

    weight_col1 = None
    weight_col2 = None
    for col in df1.columns:
        if str(col).lower().strip() in ('waga', 'weight', 'wagi'):
            weight_col1 = col
            break
    for col in df2.columns:
        if str(col).lower().strip() in ('waga', 'weight', 'wagi'):
            weight_col2 = col
            break
    weights1 = pd.to_numeric(df1[weight_col1], errors='coerce').fillna(1.0) if weight_col1 else None
    weights2 = pd.to_numeric(df2[weight_col2], errors='coerce').fillna(1.0) if weight_col2 else None
    if weight_col1:
        logger.info("Survey 1: using weight column %s", weight_col1)
    else:
        logger.info("Survey 1: no weight column, unweighted")
    if weight_col2:
        logger.info("Survey 2: using weight column %s", weight_col2)
    else:
        logger.info("Survey 2: no weight column, unweighted")

    label1 = args.label1 or "Group 1"
    label2 = args.label2 or "Group 2"
    logger.info("Labels: %s vs %s", label1, label2)

    out_dir = Path(args.output_dir or 'output')
    out_dir.mkdir(parents=True, exist_ok=True)

    c1_arg = getattr(args, 'config1', None)
    c2_arg = getattr(args, 'config2', None)
    config1_path = _resolve_config_path(c1_arg) if c1_arg else None
    config2_path = _resolve_config_path(c2_arg) if c2_arg else None
    has_c1 = config1_path and config1_path.exists()
    has_c2 = config2_path and config2_path.exists()

    if (c1_arg or c2_arg) and not (has_c1 and has_c2):
        logger.error(
            "compare: podaj oba --config1 i --config2 (istniejące pliki), albo żadnego. "
            "Otrzymano: config1=%s, config2=%s",
            config1_path, config2_path,
        )
        sys.exit(1)

    if has_c1 and has_c2:
        _cmd_compare_from_configs(
            df1, df2, weight_col1, weight_col2, weights1, weights2,
            config1_path, config2_path, label1, label2, out_dir,
        )
    else:
        _cmd_compare_legacy(
            df1, df2, weight_col1, weight_col2, weights1, weights2,
            label1, label2, out_dir,
        )


def main():
    parser = argparse.ArgumentParser(
        description='Survey Analyzer - Generate reports from survey XLSX data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable DEBUG level for more detailed logs')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # detect
    p_detect = subparsers.add_parser('detect', help='Auto-detect question types')
    p_detect.add_argument('input', help='Input XLSX file (from input/ folder if bare filename)')
    p_detect.add_argument('--output', '-o', help='Output YAML config file')

    # report
    p_report = subparsers.add_parser('report', help='Generate report')
    p_report.add_argument('input', help='Input XLSX file (from input/ folder if bare filename)')
    p_report.add_argument('--config', '-c', help='Question config YAML (from config/ if bare filename)')
    p_report.add_argument('--output-dir', '-d', default='output', help='Output directory')
    p_report.add_argument('--title', '-t', help='Report title')

    # crosstab
    p_ct = subparsers.add_parser('crosstab', help='Generate cross-tabulations')
    p_ct.add_argument('input', help='Input XLSX file (from input/ folder if bare filename)')
    p_ct.add_argument('--config', '-c', help='Question config YAML (from config/ if bare filename)')
    p_ct.add_argument('--demographics', '-g', required=True, help='Demographic vars (comma-separated)')
    p_ct.add_argument('--output-dir', '-d', default='output', help='Output directory')

    # demographic-report
    p_demo = subparsers.add_parser('demographic-report', help='Generate report with demographic breakdowns')
    p_demo.add_argument('input', help='Input XLSX file (from input/ folder if bare filename)')
    p_demo.add_argument('--config', '-c', required=True, help='Question config YAML with categorical_questions')
    p_demo.add_argument('--output-dir', '-d', default='output', help='Output directory')
    p_demo.add_argument('--title', '-t', help='Report title')

    # metric-report (M* single_choice, unweighted counts)
    p_metric = subparsers.add_parser(
        'metric-report',
        help='Raport częstości pytań M* bez wag (N surowe)',
    )
    p_metric.add_argument('input', help='Input XLSX file (from input/ folder if bare filename)')
    p_metric.add_argument('--config', '-c', required=True, help='Question config YAML (from config/ if bare filename)')
    p_metric.add_argument('--output-dir', '-d', default='output', help='Output directory')
    p_metric.add_argument('--title', '-t', help='Report title')

    # compare
    p_cmp = subparsers.add_parser('compare', help='Compare two surveys')
    p_cmp.add_argument('input1', help='First survey XLSX (from input/ folder if bare filename)')
    p_cmp.add_argument('input2', help='Second survey XLSX (from input/ folder if bare filename)')
    p_cmp.add_argument('--config1', help='YAML for first survey (mapowanie pytań po id; z config/ jeśli sama nazwa)')
    p_cmp.add_argument('--config2', help='YAML for second survey')
    p_cmp.add_argument('--label1', default='Group 1', help='Label for first survey')
    p_cmp.add_argument('--label2', default='Group 2', help='Label for second survey')
    p_cmp.add_argument('--output-dir', '-d', default='output', help='Output directory')

    args = parser.parse_args()

    _setup_logging(verbose=getattr(args, 'verbose', False))

    if args.command is None:
        parser.print_help()
        return

    if args.command == 'detect':
        cmd_detect(args)
    elif args.command == 'report':
        cmd_report(args)
    elif args.command == 'crosstab':
        cmd_crosstab(args)
    elif args.command == 'demographic-report':
        cmd_demographic_report(args)
    elif args.command == 'metric-report':
        cmd_metric_report(args)
    elif args.command == 'compare':
        cmd_compare(args)


if __name__ == '__main__':
    main()
