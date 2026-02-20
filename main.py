#!/usr/bin/env python3
"""
Survey Analyzer - Main CLI entry point.
Generates DOCX and XLSX reports from survey XLSX data files.

Usage:
  python main.py detect   <input.xlsx> [--output config.yaml]
  python main.py report   <input.xlsx> [--config config.yaml] [--output-dir ./output]
  python main.py crosstab <input.xlsx> --config config.yaml --demographics M1,M2a,M3
  python main.py compare  <file1.xlsx> <file2.xlsx> --label1 "Laity" --label2 "Clergy"
"""

import argparse
import logging
import sys
from pathlib import Path

import colorlog
import pandas as pd

from core.data_loader import (
    load_xlsx, auto_detect_questions, get_numeric_data,
    export_config, load_config,
    QT_NUMERIC_SCALE, QT_LIKERT, QT_MULTI_CHOICE, QT_SINGLE_CHOICE,
    CT_PIE, CT_FREQ_BAR, QuestionDef
)
from core.statistics import (
    descriptive_stats, frequency_table, multiple_choice_table,
    cross_tab_means, cross_tab_frequencies
)
from charts.chart_generator import (
    horizontal_bar_means, pie_chart, frequency_bar, comparison_bar
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


def _resolve_input_path(path: str) -> Path:
    """Resolve input path: bare filenames are read from input/ folder."""
    p = Path(path)
    if len(p.parts) == 1:
        return INPUT_DIR / p.name
    return p


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
        questions = load_config(str(config_path))
        logger.info("Loaded %d questions from config", len(questions))
    else:
        if args.config:
            logger.warning("Config file not found: %s (looked in %s)", args.config,
                          config_path.resolve() if config_path else args.config)
        logger.info("Step 2/6: Auto-detecting questions (no config provided)")
        questions = auto_detect_questions(df)
        logger.info("Auto-detected %d question groups", len(questions))

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

            # Determine scale for chart
            s_min = q.scale_min if q.scale_min is not None else 0
            s_max = q.scale_max if q.scale_max is not None else 10

            # For Likert with special values (6=nie wiem, 7=odmowa), cap at 5
            if q.question_type == QT_LIKERT and q.special_values:
                actual_max = max(v for v in range(1, s_max+1) if v not in q.special_values)
                s_max = actual_max

            chart_title = q.id if q.id else f"Pytanie {q_num}"
            chart_buf = horizontal_bar_means(stats, title=chart_title,
                                            scale_min=s_min, scale_max=s_max)

            report.add_section(f"{q.id}: {q.label[:80]}", level=2)
            report.add_table(stats, title="Statystyki opisowe")
            report.add_chart(chart_buf, width=6.0)

            xlsx_report.add_dataframe_sheet(stats, f"{q.id}_stats"[:31],
                                            title=f"{q.id}: {q.label[:60]}")

        elif q.question_type == QT_MULTI_CHOICE:
            q_num += 1
            logger.info("  [%s] %s... (multiple choice)", q.id, q.label[:50])

            data = get_numeric_data(df, q, weight_col)
            w = data.pop('_weight') if '_weight' in data.columns else weights
            freq = multiple_choice_table(data, w)

            chart_title = q.id if q.id else f"Pytanie {q_num}"
            chart_buf = frequency_bar(freq, title=chart_title, horizontal=True)

            report.add_section(f"{q.id}: {q.label[:80]}", level=2)
            report.add_table(freq, title="Rozkład odpowiedzi (% wskazań)")
            report.add_chart(chart_buf, width=6.0)

            xlsx_report.add_dataframe_sheet(freq, f"{q.id}_freq"[:31],
                                            title=f"{q.id}: {q.label[:60]}")

        elif q.question_type == QT_SINGLE_CHOICE:
            q_num += 1
            logger.info("  [%s] %s... (single choice)", q.id, q.label[:50])

            col_name = df.columns[q.columns[0]]
            freq = frequency_table(df[col_name], weights)

            chart_title = q.id if q.id else f"Pytanie {q_num}"
            n_cat = len(freq)

            if n_cat <= 3 and q.chart_type == CT_PIE:
                chart_buf = pie_chart(freq, title=chart_title)
            else:
                chart_buf = frequency_bar(freq, title=chart_title, horizontal=(n_cat > 4))

            report.add_section(f"{q.id}: {q.label[:80]}", level=2)
            report.add_table(freq, title="Rozkład odpowiedzi")
            report.add_chart(chart_buf, width=5.5 if n_cat <= 3 else 6.0)

            xlsx_report.add_dataframe_sheet(freq, f"{q.id}_freq"[:31],
                                            title=f"{q.id}: {q.label[:60]}")

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


def cmd_crosstab(args):
    """Generate cross-tabulation report by demographics."""
    logger.info("═══ CROSSTAB: Generating cross-tabulations ═══")
    input_path = _resolve_input_path(args.input)
    logger.info("Step 1/5: Loading Excel file from %s", input_path)
    df = load_xlsx(str(input_path), header_row=0)

    config_path = _resolve_config_path(args.config) if args.config else None
    if config_path and config_path.exists():
        logger.info("Step 2/5: Loading config from %s", config_path)
        questions = load_config(str(config_path))
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
                      q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT, QT_SINGLE_CHOICE)]
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
                    if len(ct) > 1:
                        sheet_name = f"{data_q.id}x{demo_q.id}"[:31]
                        title = f"{data_q.id} wg {demo_q.id}"
                        xlsx_ct.add_dataframe_sheet(ct, sheet_name, title)
                        break  # one sheet per question group, first item

            elif data_q.question_type == QT_SINGLE_CHOICE:
                data_col_name = df.columns[data_q.columns[0]]
                ct = cross_tab_frequencies(df[data_col_name], demo_series, weights)
                if len(ct) > 0:
                    sheet_name = f"{data_q.id}x{demo_q.id}"[:31]
                    title = f"{data_q.id} wg {demo_q.id}"
                    xlsx_ct.add_cross_tab_sheet(ct, sheet_name, title)

    logger.info("Step 5/5: Saving XLSX...")
    xlsx_path = out_dir / f"{stem}_crosstabs.xlsx"
    xlsx_ct.save(str(xlsx_path))
    logger.info("─── Cross-tab report saved to: %s ───", xlsx_path)


def cmd_compare(args):
    """Generate comparison report for two surveys."""
    logger.info("═══ COMPARE: Comparing two surveys ═══")
    input1_path = _resolve_input_path(args.input1)
    input2_path = _resolve_input_path(args.input2)
    logger.info("Step 1/5: Loading first survey from %s", input1_path)
    df1 = load_xlsx(str(input1_path), header_row=0)
    logger.info("Step 2/5: Loading second survey from %s", input2_path)
    df2 = load_xlsx(str(input2_path), header_row=0)

    logger.info("Step 3/5: Auto-detecting questions in both surveys...")
    questions1 = auto_detect_questions(df1)
    questions2 = auto_detect_questions(df2)
    logger.info("Survey 1: %d scale/likert questions | Survey 2: %d scale/likert questions",
                sum(1 for q in questions1 if q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT)),
                sum(1 for q in questions2 if q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT)))

    label1 = args.label1 or "Group 1"
    label2 = args.label2 or "Group 2"
    logger.info("Labels: %s vs %s", label1, label2)

    out_dir = Path(args.output_dir or 'output')
    out_dir.mkdir(parents=True, exist_ok=True)

    report = ReportBuilder(title=f"Porównanie: {label1} vs {label2}")
    xlsx_report = XlsxReportBuilder()
    logger.info("Step 4/5: Matching and comparing questions...")

    matched = 0
    for q1 in questions1:
        if q1.question_type not in (QT_NUMERIC_SCALE, QT_LIKERT):
            continue

        # Find matching question in survey 2 by label similarity
        best_match = None
        for q2 in questions2:
            if q2.question_type != q1.question_type:
                continue
            # Simple matching: compare first column label
            if q1.column_labels and q2.column_labels:
                l1 = q1.column_labels[0][:40]
                l2 = q2.column_labels[0][:40]
                if l1 == l2 or l1 in l2 or l2 in l1:
                    best_match = q2
                    break

        if best_match:
            matched += 1
            logger.info("  Matched [%s]: %s", q1.id, q1.label[:50])
            data1 = get_numeric_data(df1, q1)
            data2 = get_numeric_data(df2, best_match)

            stats1 = descriptive_stats(data1)
            stats2 = descriptive_stats(data2)

            s_min = q1.scale_min or 0
            s_max = q1.scale_max or 10

            chart_buf = comparison_bar(stats1, stats2, label1, label2,
                                       title=q1.id, scale_min=s_min, scale_max=s_max)

            report.add_section(f"{q1.id}: {q1.label[:80]}", level=2)

            # Combined table
            merged = stats1[['Item', 'N', 'Średnia', 'Mediana']].rename(
                columns={'N': f'N ({label1})', 'Średnia': f'Śr. ({label1})', 'Mediana': f'Med. ({label1})'}
            ).merge(
                stats2[['Item', 'N', 'Średnia', 'Mediana']].rename(
                    columns={'N': f'N ({label2})', 'Średnia': f'Śr. ({label2})', 'Mediana': f'Med. ({label2})'}
                ), on='Item', how='outer'
            )

            report.add_table(merged)
            report.add_chart(chart_buf, width=6.0)

            xlsx_report.add_dataframe_sheet(merged, f"{q1.id}_cmp"[:31])

    docx_path = out_dir / "porownanie_raport.docx"
    xlsx_path = out_dir / "porownanie_raport.xlsx"

    logger.info("Step 5/5: Saving reports...")
    report.save(str(docx_path))
    xlsx_report.save(str(xlsx_path))

    logger.info("─── Comparison complete ───")
    logger.info("Matched questions: %d", matched)
    logger.info("DOCX: %s", docx_path)
    logger.info("XLSX: %s", xlsx_path)


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

    # compare
    p_cmp = subparsers.add_parser('compare', help='Compare two surveys')
    p_cmp.add_argument('input1', help='First survey XLSX (from input/ folder if bare filename)')
    p_cmp.add_argument('input2', help='Second survey XLSX (from input/ folder if bare filename)')
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
    elif args.command == 'compare':
        cmd_compare(args)


if __name__ == '__main__':
    main()
