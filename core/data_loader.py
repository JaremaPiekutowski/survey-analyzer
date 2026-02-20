"""
Data loader and question auto-classifier for survey XLSX files.

Key design: Questions are grouped using the QID pattern (e.g. "A1.", "B3a.", "D5b.") found
in column headers. A column with a QID starts a new question group. Subsequent columns
without a QID are sub-items of that group, as long as they share the same data type.
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass, field

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

QT_NUMERIC_SCALE = "numeric_scale"
QT_LIKERT = "likert"
QT_MULTI_CHOICE = "multiple_choice"
QT_SINGLE_CHOICE = "single_choice"
QT_OPEN = "open_text"
QT_META = "metadata"

CT_HBAR_MEANS = "horizontal_bar_means"
CT_PIE = "pie"
CT_FREQ_BAR = "frequency_bar"
CT_MULTI_BAR = "multiple_choice_bar"

LIKERT_PREFIX_RE = re.compile(r'^(\d+)\s*:\s*(.+)')
QID_RE = re.compile(r'^([A-Z]\d+[a-z]?)\.\s*(.+)', re.DOTALL)

SPECIAL_VALUES = {
    'nie wiem', 'nie wiem/ nie znam', 'nie wiem/nie znam', 'nie wiem/nie znam ',
    'trudno powiedzieć', 'nie wiem/ trudno powiedzieć', 'nie wiem, trudno powiedzieć',
    'odmowa odpowiedzi', 'odmowa', '-', '', 'nan', 'none', 'nie dotyczy', 'nd', 'n/d',
}

META_KEYWORDS = [
    'numer wywiadu', 'aranżacja', 'imię', 'nazwisko', 'telefon',
    'kod pocztowy', 'miejscowość', 'waga', '[ogółem]', 'wyniki dla',
    'makroregion', 'segmentacja', 'segment',
]
EXCLUDE_KEYWORDS = ['inna, jaka', 'inne (jakie']
DEMOGRAPHIC_QIDS = {'M1', 'M1a', 'M1b', 'M2a', 'M3', 'M4', 'M5', 'M6',
                   'M7', 'M8', 'M9', 'M10', 'M11'}
EXCLUDE_QIDS = {'M2'}


@dataclass
class QuestionDef:
    id: str
    label: str
    columns: list
    column_labels: list = field(default_factory=list)
    question_type: str = ""
    chart_type: str = ""
    scale_min: Optional[int] = None
    scale_max: Optional[int] = None
    scale_labels: dict = field(default_factory=dict)
    special_values: set = field(default_factory=set)
    is_demographic: bool = False
    parent_question: str = ""
    weight_column: Optional[str] = None
    notes: str = ""


def load_xlsx(filepath: str, header_row: int = 0) -> pd.DataFrame:
    logger.info(f"Loading {filepath}")
    df = pd.read_excel(filepath, header=header_row, engine='openpyxl')
    logger.info(f"  Loaded {len(df)} rows x {len(df.columns)} columns")
    return df


def _detect_column_type(series: pd.Series) -> dict:
    values = series.dropna().astype(str).str.strip()
    values = values[values != '']
    if len(values) == 0:
        return {'type': 'empty'}
    unique = set(values)
    if unique <= {'MENTIONED', 'NOT MENTIONED'}:
        return {'type': QT_MULTI_CHOICE}
    likert_count = sum(1 for v in values if LIKERT_PREFIX_RE.match(v))
    if likert_count > len(values) * 0.4:
        nums, labels = [], {}
        for v in values:
            m = LIKERT_PREFIX_RE.match(v)
            if m:
                n = int(m.group(1))
                nums.append(n)
                labels[n] = m.group(2).strip()
        all_nums = sorted(set(nums))
        special = set()
        for n in all_nums:
            lbl = labels.get(n, '').lower()
            if any(sv in lbl for sv in ['nie wiem', 'odmowa', 'trudno']):
                special.add(n)
        valid_nums = [n for n in all_nums if n not in special]
        return {
            'type': QT_LIKERT,
            'scale_min': min(valid_nums) if valid_nums else min(all_nums),
            'scale_max': max(valid_nums) if valid_nums else max(all_nums),
            'scale_labels': labels,
            'special_numeric': special,
        }
    numeric_vals, text_vals = [], []
    for v in values:
        try:
            numeric_vals.append(float(v))
        except (ValueError, TypeError):
            if v.lower().strip() not in SPECIAL_VALUES:
                text_vals.append(v)
    if len(numeric_vals) > len(values) * 0.5 and len(text_vals) == 0:
        return {'type': QT_NUMERIC_SCALE, 'scale_min': min(numeric_vals), 'scale_max': max(numeric_vals)}
    n_unique = len(unique)
    if n_unique > 15:
        return {'type': QT_OPEN, 'n_unique': n_unique}
    return {'type': QT_SINGLE_CHOICE, 'categories': sorted(unique), 'n_unique': n_unique}


def _split_qid_header(header: str):
    """Split 'QID. Parent question text. First sub-item' into parts."""
    m = QID_RE.match(header)
    if not m:
        return None, None, header
    qid = m.group(1)
    rest = m.group(2).strip()
    # Try splitting parent text from first sub-item
    # Pattern: text ends with sentence punctuation, then sub-item starts with capital
    split_re = re.compile(r'^(.+?[.?!:;])\s+([A-ZŹŻŚĆŁÓĄĘUP].{5,})$', re.DOTALL)
    sm = split_re.match(rest)
    if sm:
        parent = f"{qid}. {sm.group(1).strip()}"
        sub = sm.group(2).strip()
        if len(sub) < len(rest) * 0.85:
            return qid, parent, sub
    return qid, f"{qid}. {rest}", None


def _is_meta(col_name: str) -> bool:
    return any(kw in col_name.lower() for kw in META_KEYWORDS)


def _should_exclude(col_name: str) -> bool:
    return any(kw in col_name.lower() for kw in EXCLUDE_KEYWORDS)


def _infer_chart_type(qtype: str, n_categories: int = 0) -> str:
    if qtype in (QT_NUMERIC_SCALE, QT_LIKERT):
        return CT_HBAR_MEANS
    elif qtype == QT_MULTI_CHOICE:
        return CT_MULTI_BAR
    elif qtype == QT_SINGLE_CHOICE:
        return CT_PIE if n_categories <= 3 else CT_FREQ_BAR
    return CT_FREQ_BAR


def auto_detect_questions(df: pd.DataFrame) -> list:
    questions = []
    col_names = list(df.columns)
    n_cols = len(col_names)

    col_types = {}
    for i in range(n_cols):
        col_types[i] = _detect_column_type(df.iloc[:, i])

    processed = set()
    seen_headers = set()
    i = 0

    while i < n_cols:
        if i in processed:
            i += 1
            continue

        col_str = str(col_names[i])
        col_norm = col_str.strip().lower()

        # Skip empty/meta/excluded/duplicates
        if (col_types[i]['type'] == 'empty' or _is_meta(col_str) or
                _should_exclude(col_str) or col_norm in seen_headers):
            processed.add(i)
            i += 1
            continue
        seen_headers.add(col_norm)

        qid, parent_text, first_sub = _split_qid_header(col_str)
        if qid and qid in EXCLUDE_QIDS:
            processed.add(i)
            i += 1
            continue

        is_demo = qid in DEMOGRAPHIC_QIDS if qid else False
        ctype = col_types[i]['type']

        # === Scale / Likert / Multi-choice: gather sub-items ===
        if ctype in (QT_LIKERT, QT_NUMERIC_SCALE, QT_MULTI_CHOICE):
            group_cols = [i]
            group_labels = [first_sub if first_sub else col_str]

            j = i + 1
            while j < n_cols:
                jcol = str(col_names[j])
                jcol_norm = jcol.strip().lower()

                # Stop at next QID column
                jqid, _, _ = _split_qid_header(jcol)
                if jqid:
                    break

                if _is_meta(jcol) or _should_exclude(jcol):
                    processed.add(j)
                    j += 1
                    continue
                if jcol_norm in seen_headers:
                    processed.add(j)
                    j += 1
                    continue

                jtype = col_types[j]['type']
                if jtype != ctype and jtype != 'empty':
                    break
                if jtype == 'empty':
                    processed.add(j)
                    j += 1
                    continue

                group_cols.append(j)
                group_labels.append(jcol)
                seen_headers.add(jcol_norm)
                j += 1

            # Merge scale info
            scale_min, scale_max = None, None
            all_labels, special = {}, set()
            for ci in group_cols:
                ct = col_types[ci]
                smin = ct.get('scale_min')
                smax = ct.get('scale_max')
                if smin is not None:
                    scale_min = smin if scale_min is None else min(scale_min, smin)
                if smax is not None:
                    scale_max = smax if scale_max is None else max(scale_max, smax)
                all_labels.update(ct.get('scale_labels', {}))
                special.update(ct.get('special_numeric', set()))

            q = QuestionDef(
                id=qid or f"group_{i}",
                label=parent_text or col_str,
                columns=group_cols,
                column_labels=group_labels,
                question_type=ctype,
                chart_type=_infer_chart_type(ctype),
                scale_min=int(scale_min) if scale_min is not None else None,
                scale_max=int(scale_max) if scale_max is not None else None,
                scale_labels=all_labels,
                special_values=special,
                is_demographic=is_demo,
            )
            questions.append(q)
            processed.update(group_cols)
            i = j
            continue

        # Single choice
        if ctype == QT_SINGLE_CHOICE:
            n_cat = col_types[i].get('n_unique', 0)
            q = QuestionDef(
                id=qid or f"choice_{i}",
                label=parent_text or col_str,
                columns=[i],
                column_labels=[col_str],
                question_type=QT_SINGLE_CHOICE,
                chart_type=_infer_chart_type(QT_SINGLE_CHOICE, n_cat),
                is_demographic=is_demo,
            )
            questions.append(q)
            processed.add(i)
            i += 1
            continue

        processed.add(i)
        i += 1

    logger.info(f"  Auto-detected {len(questions)} question groups")
    return questions


def parse_likert_value(val) -> Optional[float]:
    if val is None or str(val).strip() == '':
        return None
    s = str(val).strip()
    m = LIKERT_PREFIX_RE.match(s)
    if m:
        return float(m.group(1))
    if s.lower() in SPECIAL_VALUES:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_numeric_value(val) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in SPECIAL_VALUES:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def get_numeric_data(df: pd.DataFrame, question: QuestionDef,
                     weight_col: Optional[str] = None) -> pd.DataFrame:
    result = {}
    for col_idx, label in zip(question.columns, question.column_labels):
        col_name = df.columns[col_idx]
        series = df[col_name].copy()
        if question.question_type == QT_LIKERT:
            parsed = series.apply(parse_likert_value)
            if question.special_values:
                parsed = parsed.apply(
                    lambda x: None if x is not None and x in question.special_values else x)
        elif question.question_type == QT_NUMERIC_SCALE:
            parsed = series.apply(parse_numeric_value)
        elif question.question_type == QT_MULTI_CHOICE:
            parsed = series.apply(lambda x: 1 if str(x).strip() == 'MENTIONED' else 0)
        else:
            parsed = series
        result[label] = parsed
    result_df = pd.DataFrame(result)
    if weight_col and weight_col in df.columns:
        result_df['_weight'] = pd.to_numeric(df[weight_col], errors='coerce').fillna(1.0)
    return result_df


def export_config(questions: list, output_path: str):
    config = {'questions': []}
    for q in questions:
        qd = {
            'id': q.id, 'label': q.label, 'columns': q.columns,
            'column_labels': q.column_labels,
            'question_type': q.question_type, 'chart_type': q.chart_type,
            'is_demographic': q.is_demographic,
        }
        if q.scale_min is not None:
            qd['scale_min'] = q.scale_min
            qd['scale_max'] = q.scale_max
        if q.scale_labels:
            qd['scale_labels'] = {k: v for k, v in sorted(q.scale_labels.items())}
        if q.special_values:
            qd['special_values'] = sorted(q.special_values)
        config['questions'].append(qd)
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    logger.info(f"  Config exported to {output_path}")


def load_config(config_path: str) -> tuple[list, list | None]:
    """
    Load question config from YAML.
    Returns (questions, categorical_questions).
    categorical_questions is a list of question IDs to use as demographic breakdown dimensions,
    or None if not specified (caller should fall back to is_demographic).
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    if not config or 'questions' not in config:
        raise ValueError(f"Invalid config: missing or empty 'questions' section in {config_path}")
    questions = []
    for qd in config['questions']:
        q = QuestionDef(
            id=qd['id'], label=qd['label'], columns=qd['columns'],
            column_labels=qd.get('column_labels', []),
            question_type=qd['question_type'], chart_type=qd['chart_type'],
            scale_min=qd.get('scale_min'), scale_max=qd.get('scale_max'),
            scale_labels=qd.get('scale_labels', {}),
            special_values=set(qd.get('special_values', [])),
            is_demographic=qd.get('is_demographic', False),
        )
        questions.append(q)
    categorical_ids = config.get('categorical_questions')
    if categorical_ids is not None:
        categorical_ids = [str(x).strip() for x in categorical_ids]
    return (questions, categorical_ids)
